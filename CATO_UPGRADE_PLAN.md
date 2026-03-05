# CATO UPGRADE PLAN — v1.1.0
**Generated:** 2026-03-04
**Sources:** deep-research (30 OpenClaw complaints), socratic-mentor, DarkMirror, IdeaMatrix, RemixForge, SoSpec

---

## EXECUTIVE SUMMARY

OpenClaw has 30 documented complaints across 10 categories. The most critical:
- **CVE-2026-25253** (CVSS 8.8): RCE via auth token theft
- **"ClawJacked"**: Any website can hijack your agent
- **135,000+ exposed instances** on public internet (default binds 0.0.0.0)
- **1.5M API tokens exposed** via backend misconfiguration
- **Agent ran amok**: Meta researcher's inbox deleted while agent ignored stop commands
- **$3,600/month bills** from token waste (93.5% overhead from workspace files)
- **1.4GB installation** with 670MB unused binaries
- **820+ malicious skills** on ClawHub out of 10,700

**Cato already fixes:** credentials (AES vault), telemetry (zero), infrastructure (SQLite), cost (hard caps), supply chain (no C extensions), Windows path issues (to fix), dependency bloat (Python-only).

**Cato does NOT yet fix:** audit trail, agent runaway (reversibility gates), context token waste, skill marketplace trust, session replay.

---

## PRIORITIZED IMPLEMENTATION LIST

### P0 — SHIP IMMEDIATELY (Week 1)

**1. Hash-Chained Audit Log** `cato/audit.py` (~180 lines, NEW)
- Every tool call written to append-only SQLite table with SHA-256 chain
- Closes "agent ran amok" / "what did it do?" complaint category
- CLI: `cato audit --session <id>` exports JSONL/CSV
- Differentiator: **no competitor has tamper-evident local audit logs**

**2. Pre-Action Reversibility Gates** `cato/safety.py` (~150 lines, NEW)
- Risk-tier every browser action: READ / REVERSIBLE_WRITE / IRREVERSIBLE / HIGH_STAKES
- IRREVERSIBLE+ pauses and asks user before executing
- Addresses the Meta inbox deletion incident directly
- Config: `safety_mode: strict|permissive|off`

**3. Pre-Task Cost Forecast Gate** `budget.py` (+60 lines, MODIFY)
- Before any task executes, estimate token + Conduit cost
- Show user: "This task will cost ~$0.08. Proceed? [Y/n]"
- 3-tier alert: 20% remaining / 10% / 5% with different intervention levels
- Closes the #1 complaint category: cost surprises

**4. Windows Compatibility** `cato/platform.py` (~120 lines, NEW) + `cli.py` (MODIFY)
- `safe_path()`: normalize backslash/forward slash, expand ~
- `safe_print()`: Unicode fallback for cp1252 terminals
- `setup_signal_handlers()`: skip SIGTERM on Windows, use atexit
- `get_data_dir()`: `%APPDATA%/cato` on Windows, `~/.cato` on POSIX

### P1 — SHIP WEEK 2

**5. Conduit Bridge (opt-in browser engine)** `cato/tools/conduit_bridge.py` (~240 lines, NEW)
- Drop-in replacement for browser.py when `--browser conduit` active
- Local SQLite billing ledger (no AP2 server needed)
- Ed25519 identity simplified to local keypair (no server-side trust tiers)
- Per-action costs: NAVIGATE:1¢, CLICK:1¢, TYPE:1¢, EXTRACT:2¢, SCREENSHOT:5¢
- VOIX protocol: strips `<tool>` and `<context>` tags from extracted content
- `agent_loop.py`: route browser calls to ConduitBridge when conduit_enabled=true
- CLI: `cato start --browser conduit`, `cato migrate --browser conduit`

**6. Fare Receipt** `cato/receipt.py` (~120 lines, NEW)
- Signed, line-item billing transcript — one row per action, one hash per row
- `cato receipt --session <id>` — exports human-readable + JSONL
- Built on top of audit log (Improvement 1)
- The "taxi receipt" mechanic: shows exactly what happened and what it cost

**7. OpenClaw Migration Wizard** `migrate.py` (MODIFY, +80 lines)
- Auto-detect `~/.openclaw/` config
- Import vault keys, conversation history, custom skills
- Generate **cost comparison report**: "Last month in OpenClaw: ~$X. Estimated in Cato: ~$Y"
- This is the sales pitch, demo, and retention mechanism in one command

### P2 — SHIP WEEK 3

**8. Skill Validator** `cato/skill_validator.py` (~175 lines, NEW)
- `cato doctor --skills` validates all SKILL.md files
- Checks: YAML frontmatter, required keys, valid semver, known tool references
- Blocks loading broken skills instead of failing at runtime
- Addresses the "820+ malicious skills" OpenClaw problem at source

**9. Session Replay** `cato/replay.py` (~200 lines, NEW)
- `cato replay --session <id>`: re-run with mocked tool outputs from audit log
- Dry-run by default (no API calls, no browser)
- Produces match/mismatch diff report
- Live replay (`--live`) requires explicit budget confirmation

**10. Memory Scaling (ANN index)** `core/memory.py` (+35 lines, MODIFY)
- Activate hnswlib index automatically when chunk count > 5,000
- Silent fallback to brute-force if hnswlib not installed
- Zero config change required

**11. Vault Canary** `vault.py` (+30 lines, MODIFY)
- Store one synthetic dummy API key alongside real keys
- If it's ever used externally, fire an immediate alert
- 2-hour build, high trust signal

**12. `cato doctor --attest`** `cli.py` (+40 lines, MODIFY)
- Emit signed JSON attestation of security properties
- CI-assertable: `cato doctor --attest | jq .vault_encrypted` returns `true`
- Closes "prove it" gap in 60 seconds for skeptical developers

### P3 — FUTURE

**13. Amnesiac Session Profiles** — Memory off by default, named profiles
**14. Outcome Billing Engine** — Pay for EXTRACT_TABLE result, not per-click
**15. Sentinel Mode** — Watchdog daemon: monitors costs, runs self-tests, daily digest

---

## CONDUIT INTEGRATION DECISION

**Selected: Option B — Opt-In alongside existing browser.py**

Rationale:
- Cato's philosophy IS its product — forcing billing on local users destroys trust
- One config line: `conduit_enabled: true` (zero impact on existing users)
- `cato start --browser conduit` is the activation path
- Local-only billing (SQLite ledger, no AP2 server)
- Ed25519 identity for audit trail integrity only (no server-side trust tiers)
- Option C (Pro Tier) only if commercial tier becomes necessary

---

## CATO'S POSITIONING

**3-word tag: "Auditable by default."**

OpenClaw = "The agent platform for everything" (feature race)
Cato = "Auditable by default" (architectural property OpenClaw cannot copy without a rewrite)

**60-second pitch:**
> OpenClaw has 135,000 exposed instances, a $3,600/month billing surprise problem, and an agent that deleted a Meta researcher's inbox while ignoring stop commands. Cato is 3,000 lines of Python you can read in a coffee break — no Docker, no open ports by default, hard budget caps before every API call, and a tamper-evident audit log of everything your agent did. One command to migrate from OpenClaw. Your history comes with you.

---

## FILES TO CREATE/MODIFY

| File | Action | Lines |
|------|--------|-------|
| `cato/audit.py` | NEW | ~180 |
| `cato/safety.py` | NEW | ~150 |
| `cato/platform.py` | NEW | ~120 |
| `cato/receipt.py` | NEW | ~120 |
| `cato/skill_validator.py` | NEW | ~175 |
| `cato/replay.py` | NEW | ~200 |
| `cato/tools/conduit_bridge.py` | NEW | ~240 |
| `budget.py` | MODIFY | +60 |
| `migrate.py` | MODIFY | +80 |
| `vault.py` | MODIFY | +30 |
| `core/memory.py` | MODIFY | +35 |
| `cli.py` | MODIFY | +100 |
| `agent_loop.py` | MODIFY | +20 |
| `config.py` | MODIFY | +15 |

**Total: ~1,825 lines new/modified. Zero new infrastructure. SQLite only.**
