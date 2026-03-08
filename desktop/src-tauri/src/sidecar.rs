//! Sidecar management for the Cato Python daemon.
//!
//! Spawns `cato start --channel webchat` as a child process and monitors its health.
//! Gracefully shuts down on app exit.

use std::process::Stdio;
use tokio::process::{Child, Command};
use tokio::time::{sleep, Duration};

/// Manages the Cato daemon sidecar process.
pub struct SidecarManager {
    child: Option<Child>,
    http_port: u16,
    ws_port: u16,
}

impl SidecarManager {
    pub fn new(http_port: u16, ws_port: u16) -> Self {
        Self {
            child: None,
            http_port,
            ws_port,
        }
    }

    pub fn http_port(&self) -> u16 {
        self.http_port
    }

    pub fn ws_port(&self) -> u16 {
        self.ws_port
    }

    /// Check if the daemon is running — either as a child process we spawned,
    /// or as an externally-started daemon already listening on the HTTP port.
    ///
    /// This handles the case where the user started `cato start` manually before
    /// opening the desktop app: the child is None, but port 8080 is accepting
    /// HTTP requests, so we should still report running = true.
    pub async fn is_running(&mut self) -> bool {
        // 1. If we spawned a child, check it first
        if let Some(ref mut child) = self.child {
            match child.try_wait() {
                Ok(Some(_status)) => {
                    // Process has exited — clean up and fall through to HTTP check
                    self.child = None;
                }
                Ok(None) => return true,   // Our child is still alive
                Err(_) => {
                    self.child = None;
                }
            }
        }

        // 2. No child (never started, or it exited) — check if daemon is
        //    reachable on the HTTP port (external process or race condition).
        self.check_http_health().await
    }

    /// Return true if the daemon health endpoint responds with HTTP 200.
    async fn check_http_health(&self) -> bool {
        let url = format!("http://127.0.0.1:{}/health", self.http_port);
        let client = reqwest::Client::new();
        matches!(
            client.get(&url).timeout(std::time::Duration::from_millis(800)).send().await,
            Ok(resp) if resp.status().is_success()
        )
    }

    /// Start the Cato daemon as a child process.
    ///
    /// Tries the bundled sidecar binary first, falls back to system `cato`.
    pub async fn start(&mut self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Check if already running (handle crashed state)
        if self.is_running().await {
            return Ok(());
        }

        let cato_bin = Self::find_cato_binary();

        // Clear any stale PID file by running `cato stop` first (ignores errors)
        log::info!("Clearing any stale Cato daemon state...");
        let _ = Command::new(&cato_bin).args(["stop"]).output().await;
        sleep(Duration::from_millis(500)).await;

        log::info!("Starting Cato daemon: {} start --channel webchat", cato_bin);

        // Read vault password from the Cato .env file so the daemon can unlock
        // credentials (Telegram token, API keys) without an interactive prompt.
        let vault_password = Self::read_vault_password();

        let mut cmd = Command::new(&cato_bin);
        cmd.args(["start", "--channel", "webchat"])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);

        if let Some(pw) = vault_password {
            cmd.env("CATO_VAULT_PASSWORD", pw);
        }

        let child = cmd.spawn().map_err(|e| {
            format!("Failed to spawn Cato daemon ({}): {}", cato_bin, e)
        })?;

        self.child = Some(child);

        // Wait for the daemon to become healthy (up to 30 seconds)
        self.wait_for_health(30).await?;

        log::info!("Cato daemon is healthy on port {}", self.http_port);
        Ok(())
    }

    /// Stop the Cato daemon gracefully.
    pub async fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            log::info!("Stopping Cato daemon...");

            // Try graceful shutdown via `cato stop`
            let cato_bin = Self::find_cato_binary();
            let _ = Command::new(&cato_bin)
                .args(["stop"])
                .output()
                .await;

            // Wait up to 5 seconds for the process to exit
            let timeout = sleep(Duration::from_secs(5));
            tokio::pin!(timeout);

            tokio::select! {
                _ = child.wait() => {
                    log::info!("Cato daemon stopped gracefully");
                }
                _ = &mut timeout => {
                    log::warn!("Cato daemon did not stop in time, killing...");
                    let _ = child.kill().await;
                }
            }
        }
    }

    /// Poll the health endpoint until the daemon is ready.
    async fn wait_for_health(
        &self,
        timeout_secs: u64,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let url = format!("http://127.0.0.1:{}/health", self.http_port);
        let client = reqwest::Client::new();
        let deadline = tokio::time::Instant::now() + Duration::from_secs(timeout_secs);

        loop {
            if tokio::time::Instant::now() >= deadline {
                return Err("Cato daemon health check timed out".into());
            }

            match client.get(&url).timeout(Duration::from_secs(2)).send().await {
                Ok(resp) if resp.status().is_success() => return Ok(()),
                _ => {}
            }

            sleep(Duration::from_millis(500)).await;
        }
    }

    /// Read CATO_VAULT_PASSWORD from the Cato .env file.
    /// Returns None if not set (daemon will start without vault access).
    fn read_vault_password() -> Option<String> {
        // Already set in environment — use it directly
        if let Ok(pw) = std::env::var("CATO_VAULT_PASSWORD") {
            if !pw.is_empty() {
                return Some(pw);
            }
        }

        // Try to read from the project .env file
        let cato_dir = dirs::home_dir()?.join("Desktop").join("Cato");
        let env_path = cato_dir.join(".env");
        if let Ok(contents) = std::fs::read_to_string(&env_path) {
            for line in contents.lines() {
                if let Some(val) = line.strip_prefix("CATO_VAULT_PASSWORD=") {
                    let pw = val.trim().to_string();
                    if !pw.is_empty() {
                        log::info!("Loaded CATO_VAULT_PASSWORD from .env");
                        return Some(pw);
                    }
                }
            }
        }

        None
    }

    /// Find the cato binary — bundled sidecar → known install paths → PATH (dev only).
    ///
    /// Security: avoids resolving bare "cato" from CWD on Windows (PATH hijacking).
    /// Checks absolute locations before falling back to PATH resolution.
    fn find_cato_binary() -> String {
        // 1. Bundled alongside the app binary
        if let Ok(exe) = std::env::current_exe() {
            let sidecar = exe.parent().unwrap_or(exe.as_path()).join("cato");
            if sidecar.exists() {
                return sidecar.to_string_lossy().to_string();
            }
        }

        // 2. Known absolute install locations (Windows editable pip install)
        let known_paths = [
            r"C:\Users\Administrator\AppData\Roaming\Python\Python312\Scripts\cato.exe",
            r"C:\Users\Administrator\.local\bin\cato.exe",
            r"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\Scripts\cato.exe",
            r"C:\Program Files\Python312\Scripts\cato.exe",
        ];
        for path in &known_paths {
            if std::path::Path::new(path).exists() {
                return path.to_string();
            }
        }

        // 3. Resolve via PATH using `where` (Windows) to get the full absolute path.
        //    This is safer than passing a bare name to Command::new which would
        //    search CWD first on some Windows configurations.
        if let Ok(output) = std::process::Command::new("where").arg("cato").output() {
            if let Ok(stdout) = std::str::from_utf8(&output.stdout) {
                if let Some(line) = stdout.lines().next() {
                    let abs_path = line.trim().to_string();
                    if !abs_path.is_empty() {
                        log::info!("Resolved cato via PATH: {}", abs_path);
                        return abs_path;
                    }
                }
            }
        }

        // Final fallback — development only
        log::warn!("cato binary not found at known locations; falling back to bare 'cato'");
        "cato".to_string()
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _: Result<(), std::io::Error> = child.start_kill();
        }
    }
}
