# Genesis Pipeline
**Version:** 1.0.0
**Capabilities:** pipeline.run → EmpireRuntime, invoke_for_genesis_phase, checkpoint resume

## Trigger Phrases
"build a business", "run genesis", "start the pipeline", "run phase", "resume pipeline",
"skip completed", "genesis build", "empire run"

## Phase Map

| # | Name | Primary | Fallback | Timeout |
|---|------|---------|----------|---------|
| 1 | Market Research | claude | — | 180 s |
| 2 | SEO + Marketing | claude | — | 120 s |
| 3 | Design System | gemini | claude | 120 s |
| 4 | Technical Spec | claude | codex | 150 s |
| 5 | Construction | claude | codex | 600 s |
| 6 | Test + Fix | codex | claude | 300 s |
| 7 | Deploy (GATE) | claude | — | 240 s |
| 8 | Marketing Auto | claude | — | 120 s |
| 9 | Health | claude | — | 60 s |

## Rules
1. `skip_completed=True` resumes — skips phases with `success=True` checkpoint
2. `stop_for_approval=True` pauses after phase 7 completes, before phase 8 — requires `through_phase > 7`
3. All CLIs invoked with `-p <prompt>` flag (subprocess, not stdin pipe)
4. Phase 6 uses `codex --full-auto`; workdir = `<business_dir>/website`
5. `degraded=True` from both primary + fallback → Andon Cord: ask user
6. Write failed checkpoint (`success=False`) so `skip_completed` won't skip on retry

<!-- COLD -->

## Key APIs

```python
# Start (phases 1-9, gate after phase 7)
from cato.pipeline.runtime import EmpireRuntime
runtime = EmpireRuntime()
run = runtime.create_business_scaffold("SaaS idea")
await runtime.run_pipeline(
    business_slug=run.business_slug,
    start_phase=1,
    through_phase=9,        # must be > 7 for the approval gate to fire
    stop_for_approval=True, # pauses after phase 7, sets status=AWAITING_APPROVAL
    skip_completed=False,
)

# Resume (skip completed phases)
await runtime.run_pipeline(
    business_slug="my-saas",
    start_phase=1,
    through_phase=9,        # must be > 7 for the approval gate to fire
    stop_for_approval=True,
    skip_completed=True,    # skips phases where checkpoint has success=True
)

# Single phase via CLI router
from cato.orchestrator.cli_invoker import invoke_for_genesis_phase
from cato.pipeline.phase_library import EmpirePhaseLibrary
bundle = EmpirePhaseLibrary().build_prompt(run, phase=4)
result = await invoke_for_genesis_phase(4, bundle.prompt, run.business_slug)

# Write checkpoint after phase succeeds
store.write_phase_checkpoint(run_id, phase=3, payload={"success": True, "worker": "gemini"})

# Check if phase is complete
complete = runtime._phase_is_complete(run, phase=3)  # True / False
```

<!-- For full per-phase reference, shell invocation patterns, degraded handling,
     and directory structure, load the runtime skill:
     ~/.cato/skills/genesis-pipeline/SKILL.md -->
