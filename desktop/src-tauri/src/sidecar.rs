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

    pub fn is_running(&self) -> bool {
        self.child.is_some()
    }

    /// Start the Cato daemon as a child process.
    ///
    /// Tries the bundled sidecar binary first, falls back to system `cato`.
    pub async fn start(&mut self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        if self.child.is_some() {
            return Ok(()); // Already running
        }

        // Try to find the cato binary
        let cato_bin = Self::find_cato_binary();

        log::info!("Starting Cato daemon: {} start --channel webchat", cato_bin);

        let child = Command::new(&cato_bin)
            .args(["start", "--channel", "webchat"])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .map_err(|e| {
                format!("Failed to spawn Cato daemon ({}): {}", cato_bin, e)
            })?;

        self.child = Some(child);

        // Wait for the daemon to become healthy (up to 15 seconds)
        self.wait_for_health(15).await?;

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

    /// Find the cato binary — try sidecar path first, then PATH.
    fn find_cato_binary() -> String {
        // In a bundled app, the sidecar would be at a known location.
        // For development, just use the system `cato` command.
        if let Ok(exe) = std::env::current_exe() {
            let sidecar = exe.parent().unwrap_or(exe.as_path()).join("cato");
            if sidecar.exists() {
                return sidecar.to_string_lossy().to_string();
            }
        }

        // Fallback: assume `cato` is on PATH (works during development)
        "cato".to_string()
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        // Kill the child process if it's still running when the manager is dropped.
        // This is a last resort — prefer calling stop() explicitly.
        if let Some(mut child) = self.child.take() {
            let _: Result<(), std::io::Error> = child.start_kill();
        }
    }
}
