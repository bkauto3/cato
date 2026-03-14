//! Sidecar management for the Cato Python daemon.
//!
//! Spawns `cato start --channel webchat` as a child process and monitors its health.
//! Gracefully shuts down on app exit.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tokio::io::{AsyncBufReadExt, AsyncRead, BufReader};
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
    /// opening the desktop app: the child is None, but the daemon health route
    /// is still responding on the discovered HTTP port.
    pub async fn is_running(&mut self) -> bool {
        self.refresh_ports_from_disk();

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

        self.refresh_ports_from_disk();

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
        let sidecar_env = Self::load_env_file();

        // Clear any stale PID file by running `cato stop` first (ignores errors)
        log::info!("Clearing any stale Cato daemon state...");
        let _ = Command::new(&cato_bin).args(["stop"]).output().await;
        sleep(Duration::from_millis(500)).await;

        log::info!(
            "Starting Cato daemon: {} start --channel webchat",
            cato_bin.display()
        );

        let mut cmd = Command::new(&cato_bin);
        cmd.args(["start", "--channel", "webchat"])
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);

        for (key, value) in &sidecar_env {
            if std::env::var_os(key).is_none() {
                cmd.env(key, value);
            }
        }

        let mut child = cmd.spawn().map_err(|e| {
            format!("Failed to spawn Cato daemon ({}): {}", cato_bin.display(), e)
        })?;

        if let Some(stdout) = child.stdout.take() {
            Self::spawn_log_drain(stdout, false);
        }
        if let Some(stderr) = child.stderr.take() {
            Self::spawn_log_drain(stderr, true);
        }

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
        &mut self,
        timeout_secs: u64,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let client = reqwest::Client::new();
        let deadline = tokio::time::Instant::now() + Duration::from_secs(timeout_secs);

        loop {
            if tokio::time::Instant::now() >= deadline {
                return Err("Cato daemon health check timed out".into());
            }

            self.refresh_ports_from_disk();
            let url = format!("http://127.0.0.1:{}/health", self.http_port);
            match client.get(&url).timeout(Duration::from_secs(2)).send().await {
                Ok(resp) if resp.status().is_success() => return Ok(()),
                _ => {}
            }

            sleep(Duration::from_millis(500)).await;
        }
    }

    fn refresh_ports_from_disk(&mut self) {
        let Some(port_path) = Self::port_file_path() else {
            return;
        };

        let Ok(raw_port) = std::fs::read_to_string(&port_path) else {
            return;
        };

        let Ok(http_port) = raw_port.trim().parse::<u16>() else {
            log::warn!("Invalid port file contents in {}", port_path.display());
            return;
        };

        self.http_port = http_port;
        // Desktop chat and coding-agent traffic both ride the aiohttp /ws surface.
        self.ws_port = http_port;
    }

    fn spawn_log_drain<R>(reader: R, is_stderr: bool)
    where
        R: AsyncRead + Unpin + Send + 'static,
    {
        tauri::async_runtime::spawn(async move {
            let mut lines = BufReader::new(reader).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                let line = line.trim();
                if line.is_empty() {
                    continue;
                }
                if is_stderr {
                    log::warn!("[cato] {}", line);
                } else {
                    log::info!("[cato] {}", line);
                }
            }
        });
    }

    /// Load supplemental environment variables from the standard Cato .env locations.
    /// Existing process env vars always win over values from disk.
    fn load_env_file() -> BTreeMap<String, String> {
        for env_path in Self::env_file_candidates() {
            if !env_path.exists() {
                continue;
            }

            match std::fs::read_to_string(&env_path) {
                Ok(contents) => {
                    let parsed = Self::parse_dotenv(&contents);
                    if !parsed.is_empty() {
                        log::info!("Loaded sidecar environment from {}", env_path.display());
                        return parsed;
                    }
                }
                Err(err) => {
                    log::warn!("Failed to read {}: {}", env_path.display(), err);
                }
            }
        }

        BTreeMap::new()
    }

    fn env_file_candidates() -> Vec<PathBuf> {
        let mut candidates = Vec::new();

        if let Ok(path) = std::env::var("CATO_ENV_FILE") {
            let path = PathBuf::from(path);
            if path.is_absolute() {
                candidates.push(path);
            } else if let Ok(cwd) = std::env::current_dir() {
                candidates.push(cwd.join(path));
            }
        }

        if let Some(data_dir) = Self::cato_data_dir() {
            candidates.push(data_dir.join(".env"));
        }

        if let Some(base_dir) = Self::current_exe_base_dir() {
            candidates.push(base_dir.join(".env"));
        }

        if let Ok(cwd) = std::env::current_dir() {
            candidates.push(cwd.join(".env"));
        }

        candidates
    }

    fn parse_dotenv(contents: &str) -> BTreeMap<String, String> {
        let mut out = BTreeMap::new();

        for raw_line in contents.lines() {
            let line = raw_line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }

            let line = line.strip_prefix("export ").unwrap_or(line);
            let Some((key, value)) = line.split_once('=') else {
                continue;
            };

            let key = key.trim();
            if key.is_empty() {
                continue;
            }

            let value = value.trim();
            let value = if value.len() >= 2
                && ((value.starts_with('"') && value.ends_with('"'))
                    || (value.starts_with('\'') && value.ends_with('\'')))
            {
                value[1..value.len() - 1].to_string()
            } else {
                value.to_string()
            };

            out.insert(key.to_string(), value);
        }

        out
    }

    fn cato_data_dir() -> Option<PathBuf> {
        if cfg!(windows) {
            dirs::config_dir().map(|dir| dir.join("cato"))
        } else {
            dirs::home_dir().map(|dir| dir.join(".cato"))
        }
    }

    fn port_file_path() -> Option<PathBuf> {
        Self::cato_data_dir().map(|dir| dir.join("cato.port"))
    }

    fn current_exe_base_dir() -> Option<PathBuf> {
        let exe = std::env::current_exe().ok()?;
        let exe_dir = exe.parent()?;
        if exe_dir.ends_with("deps") {
            Some(exe_dir.parent().unwrap_or(exe_dir).to_path_buf())
        } else {
            Some(exe_dir.to_path_buf())
        }
    }

    fn platform_binary_path(base: PathBuf) -> PathBuf {
        #[cfg(windows)]
        {
            if base.extension().is_none() {
                let mut path = base;
                path.set_extension("exe");
                return path;
            }
        }

        #[cfg(not(windows))]
        {
            if base.extension().is_some_and(|ext| ext == "exe") {
                let mut path = base;
                path.set_extension("");
                return path;
            }
        }

        base
    }

    fn is_placeholder_sidecar(path: &Path) -> bool {
        let Ok(metadata) = std::fs::metadata(path) else {
            return false;
        };

        if metadata.len() > 512 {
            return false;
        }

        let Ok(contents) = std::fs::read(path) else {
            return false;
        };

        contents.starts_with(b"placeholder sidecar stub;")
    }

    fn dev_sidecar_candidates(base_dir: &Path) -> Vec<PathBuf> {
        let mut candidates = Vec::new();

        let target = std::env::var("TARGET").ok();
        let mut triple = target.unwrap_or_else(|| {
            #[cfg(target_os = "windows")]
            let suffix = "pc-windows-msvc";
            #[cfg(target_os = "macos")]
            let suffix = "apple-darwin";
            #[cfg(all(not(target_os = "windows"), not(target_os = "macos")))]
            let suffix = "unknown-linux-gnu";

            #[cfg(target_arch = "x86_64")]
            let arch = "x86_64";
            #[cfg(target_arch = "aarch64")]
            let arch = "aarch64";

            format!("{arch}-{suffix}")
        });

        if cfg!(windows) && !triple.ends_with(".exe") {
            triple.push_str(".exe");
        }

        // Development launches often run directly from target/release, while the
        // staged sidecar still lives under src-tauri/binaries.
        let dev_binary = base_dir
            .parent()
            .and_then(|dir| dir.parent())
            .map(|dir| dir.join("binaries").join(format!("cato-{triple}")));

        if let Some(path) = dev_binary {
            candidates.push(path);
        }

        candidates
    }

    fn path_lookup_binary() -> Option<PathBuf> {
        #[cfg(windows)]
        let resolver = "where";
        #[cfg(not(windows))]
        let resolver = "which";

        let output = std::process::Command::new(resolver)
            .arg("cato")
            .output()
            .ok()?;

        if !output.status.success() {
            return None;
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        stdout
            .lines()
            .map(str::trim)
            .find(|line| !line.is_empty())
            .map(PathBuf::from)
            .filter(|path| path.exists())
    }

    /// Find the cato binary — env override → bundled sidecar → PATH (dev only).
    fn find_cato_binary() -> PathBuf {
        if let Ok(path) = std::env::var("CATO_SIDECAR_PATH") {
            let override_path = PathBuf::from(path);
            if override_path.exists() {
                log::info!(
                    "Using Cato sidecar from CATO_SIDECAR_PATH: {}",
                    override_path.display()
                );
                return override_path;
            }
            log::warn!(
                "CATO_SIDECAR_PATH points to a missing file: {}",
                override_path.display()
            );
        }

        if let Some(base_dir) = Self::current_exe_base_dir() {
            let bundled = Self::platform_binary_path(base_dir.join("binaries").join("cato"));
            if bundled.exists() {
                return bundled;
            }

            let adjacent = Self::platform_binary_path(base_dir.join("cato"));
            if adjacent.exists() && !Self::is_placeholder_sidecar(&adjacent) {
                return adjacent;
            }

            for candidate in Self::dev_sidecar_candidates(&base_dir) {
                if candidate.exists() && !Self::is_placeholder_sidecar(&candidate) {
                    log::info!("Using development sidecar: {}", candidate.display());
                    return candidate;
                }
            }
        }

        if let Some(path) = Self::path_lookup_binary() {
            log::info!("Resolved cato via PATH: {}", path.display());
            return path;
        }

        log::warn!("cato binary not bundled; falling back to bare 'cato' for development");
        Path::new("cato").to_path_buf()
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _: Result<(), std::io::Error> = child.start_kill();
        }
    }
}
