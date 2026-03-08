"""Minimal runner script for the Cato daemon — used by Task Scheduler / NSSM."""
import os, sys, logging
from pathlib import Path

os.chdir(r"C:\Users\Administrator\Desktop\Cato")
sys.path.insert(0, r"C:\Users\Administrator\Desktop\Cato")

# Vault password — baked in so no env var needed when run as SYSTEM
os.environ.setdefault("CATO_VAULT_PASSWORD", "mypassword123")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

try:
    from dotenv import load_dotenv
    load_dotenv(r"C:\Users\Administrator\Desktop\Cato\.env")
except ImportError:
    pass

from cato.cli import CatoConfig, Vault, BudgetManager, _CATO_DIR, _run_daemon, _PID_FILE

vault_path = _CATO_DIR / "vault.enc"
vault = Vault(vault_path=vault_path) if vault_path.exists() else None
config = CatoConfig.load()
budget = BudgetManager(session_cap=config.session_cap, monthly_cap=config.monthly_cap)

if _PID_FILE.exists():
    _PID_FILE.unlink(missing_ok=True)
_PID_FILE.write_text(str(os.getpid()))

try:
    _run_daemon(config, "claude", "all")
finally:
    _PID_FILE.unlink(missing_ok=True)
