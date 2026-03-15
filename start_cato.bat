@echo off
set CATO_VAULT_PASSWORD=mypassword123
cd /d C:\Users\Administrator\Desktop\Cato
python -c "
import os, sys, logging
logging.basicConfig(level=logging.INFO, format='%%(asctime)s %%(name)s %%(levelname)s %%(message)s')
os.chdir(r'C:\Users\Administrator\Desktop\Cato')
from cato.cli import CatoConfig, Vault, BudgetManager, _CATO_DIR, _run_daemon, safe_print, _PID_FILE, setup_signal_handlers
from pathlib import Path
import os as _os

vault_path = _CATO_DIR / 'vault.enc'
vault = Vault(vault_path=vault_path) if vault_path.exists() else None
config = CatoConfig.load()
budget = BudgetManager(session_cap=config.session_cap, monthly_cap=config.monthly_cap)

if _PID_FILE.exists():
    _PID_FILE.unlink()

_PID_FILE.write_text(str(_os.getpid()))

def _shutdown():
    _PID_FILE.unlink(missing_ok=True)

setup_signal_handlers(_shutdown)
try:
    _run_daemon(config, 'claude', 'all')
finally:
    _PID_FILE.unlink(missing_ok=True)
"
