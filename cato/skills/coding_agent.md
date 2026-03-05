# Coding Agent
**Version:** 1.0.0
**Capabilities:** shell.exec → claude CLI, codex CLI, gemini CLI

## Overview
Delegates coding tasks to the LLM CLIs installed on this machine:
- `claude` (Claude Code) — at `/c/Users/Administrator/.local/bin/claude`
- `codex` — OpenAI Codex CLI (`codex exec --full-auto`)
- `gemini` — Google Gemini CLI (stdin-pipe only, never `--model` flag)

All invocations run via the `shell` tool. Background execution is handled by
running the command in a shell background process via `start /B` (Windows) or `&` (bash).

---

## Agent Selection

| Task | CLI | Flags | Notes |
|------|-----|-------|-------|
| Code generation, feature builds | **codex** | `--full-auto` | Sandboxed auto-approves all writes |
| Research, analysis, writing | **claude** | (none) | Non-interactive, reads/writes files |
| Design systems, visual reasoning | **gemini** | stdin pipe only | `cat prompt.md \| gemini` |
| PR review | **codex** | (none, vanilla) | No side effects |
| Ad-hoc fixes | **codex** | `--full-auto` | Fastest for targeted code changes |

---

## Instructions

### Running Codex (building / fixing code)

Use `--full-auto` for any task that writes files:

```
shell.exec:
  command: codex exec --full-auto "Your task description here"
  workdir: C:\path\to\project
```

**CRITICAL:** Never run Codex from `~/.cato/` or `~/.claude/` — always set
`workdir` to the target project directory so it stays scoped.

**Resuming a stuck Codex session:**
```
shell.exec:
  command: codex exec --full-auto "Resume from where you left off. Read progress notes first."
  workdir: C:\path\to\project
```

### Running Claude Code

```
shell.exec:
  command: claude "Your task description"
  workdir: C:\path\to\project
```

Claude Code works best for: post-deploy validation, running Python scripts,
reading/writing structured files, tasks that need the full tool ecosystem.

### Running Gemini CLI

**ALWAYS pipe via stdin. NEVER use `--model` flag.**

```
shell.exec:
  command: cat prompt.md | gemini
  workdir: C:\path\to\project
```

With variable substitution:
```
shell.exec:
  command: cat prompt.md | sed "s/{VAR}/value/g" | gemini
  workdir: C:\path\to\project
```

**Why stdin-only:** Gemini CLI auto-enters headless/non-interactive mode when
stdin is a pipe. The `--model` flag breaks headless detection → `ModelNotFoundError`.

---

## Monitoring Long-Running Tasks

After launching a CLI task in the background, poll with shell.exec:

```
shell.exec:
  command: tasklist | findstr codex
```

To read output from a running process, redirect stdout to a log file:
```
shell.exec:
  command: codex exec --full-auto "Build X" > C:\Temp\codex_out.txt 2>&1
  workdir: C:\path\to\project
```

Then tail:
```
shell.exec:
  command: powershell Get-Content C:\Temp\codex_out.txt -Tail 30
```

---

## Rules

1. **Respect the CLI choice** — if user asks for Codex, use Codex. Never substitute.
2. **workdir matters** — always scope to target project, never the Cato data dir.
3. **--full-auto for building** — required for Codex to auto-approve file writes.
4. **Gemini = stdin pipe only** — no `--model` flag, ever.
5. **Monitor long tasks** — redirect to a log file and tail it. Don't fire-and-forget.
6. **Budget check** — shell.exec costs count toward session budget. Warn user if a
   task may run many iterations.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModelNotFoundError` from Gemini | Remove `--model` flag. Use `cat prompt.md \| gemini` |
| Codex exits before finishing | Re-run with `"Resume from where you stopped"` |
| `claude` not found | Full path: `/c/Users/Administrator/.local/bin/claude "task"` |
| Codex hangs on `npm install` prompt | Add `--yes` or pre-run `npm install` separately |
| Output too large to read inline | Redirect to file: `command > out.txt 2>&1`, then tail |
