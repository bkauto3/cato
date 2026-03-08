# CATO — MANDATORY DEVELOPMENT RULES

## AUDIT GATE: NOTHING GETS PUSHED TO GITHUB WITHOUT PASSING THIS PIPELINE

Every change — no matter how small — must pass through the full audit pipeline before any `git push`:

```
CODE COMPLETE
     |
     v
[1] ALEX AGENT — Audit & Test
     - Full code review of all changed files
     - Run complete test suite (must be 100% passing — no exceptions)
     - Identify and fix all issues found
     - Produce audit report: CATO_ALEX_AUDIT.md
     - Status must be: APPROVED
     |
     v
[2] KRAKEN AGENT — Verification & Reality Check
     - Verify Alex's audit is authentic and complete
     - Independently verify test results
     - Implement any additional fixes Kraken deems necessary
     - Produce verdict: CATO_KRAKEN_VERDICT.md
     - Status must be: APPROVED
     |
     v
[3] GIT PUSH — Only after both agents approve
```

## THE THREE LAWS

1. **100% test pass rate** — no exceptions, ever. One failing test = do not push.
2. **Alex audits first** — always. No skipping, no "it's a small change."
3. **Kraken verifies second** — always. Kraken's verdict is final.

## AUDIT AGENT DETAILS

### Alex (Audit & Test Agent)
- Performs full code review of all changed files
- Runs `pytest` — must see 100% pass before approving
- Fixes bugs found during review
- Writes `CATO_ALEX_AUDIT.md` with findings, fixes, and APPROVED/REJECTED status

### Kraken (Verification Agent)
- Reviews Alex's audit report for completeness and authenticity
- Re-runs tests independently to confirm results
- Applies any additional fixes Kraken identifies
- Writes `CATO_KRAKEN_VERDICT.md` with final GO/NO-GO decision
- Kraken's GO is the only authorization to push

## WHAT THIS APPLIES TO

- All Python source changes (`cato/`, `tests/`)
- All frontend changes (`desktop/src/`, `cato/ui/`)
- All configuration changes (`pyproject.toml`, `Cargo.toml`, etc.)
- All new files added to the repo
- ALL commits intended for the `main` branch

## PROJECT OVERVIEW

**Cato** — Privacy-focused AI agent daemon. Alternative to OpenClaw/ClawdBot.
- Python 3.11+, asyncio, aiohttp, websockets
- Tauri v2 desktop app (`desktop/`) — React 19 + TypeScript + Rust sidecar
- SQLite memory, YAML config, AES-256-GCM vault
- Ports: HTTP 8080, WS 8081 (canonical defaults)
- Live install: `pip install -e .` at this directory

## KEY DIRECTORIES

```
cato/                  Python daemon source
  api/                 aiohttp web + WebSocket handlers
  orchestrator/        Multi-model CLI fan-out (Claude/Codex/Gemini/Cursor)
  audit/               Hash-chained audit log
  core/                Memory, context, scheduling
  ui/                  Web UI (coding_agent.html)
desktop/               Tauri v2 desktop app
  src/                 React/TypeScript frontend
  src-tauri/           Rust sidecar
tests/                 pytest test suite (1285+ tests, must stay 100%)
```

## AUDIT REPORT LOCATIONS

- Alex audit: `CATO_ALEX_AUDIT.md` (repo root)
- Kraken verdict: `CATO_KRAKEN_VERDICT.md` (repo root)
- Historical verdicts: `KRAKEN_VERDICT_*.md`
