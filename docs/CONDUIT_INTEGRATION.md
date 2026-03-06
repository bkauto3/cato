# Conduit integration (config-driven)

When Conduit is enabled (`conduit_enabled: true` in config), Cato uses a config-driven Conduit bridge so that extraction limits, crawl delay, selector healing, and vault come from **CatoConfig**.

## Creating the bridge

**Use the config-driven constructor everywhere:**

```python
from cato.config import CatoConfig
from cato.platform import get_data_dir
from cato.tools.conduit_bridge import ConduitBridge

cfg = CatoConfig.load()  # or your runtime config
session_id = "my-session"

bridge = ConduitBridge(
    cfg.to_conduit_bridge_config(
        session_id,
        data_dir=str(get_data_dir()),
        conduit_budget_per_session=cfg.conduit_budget_per_session,
    ),
    session_id,
)
await bridge.start()
# ... use bridge ...
await bridge.stop()
```

**Do not** use the legacy form `ConduitBridge(session_id, budget_cents=..., data_dir=...)` in new code; it leaves `_config` empty so extraction/crawl/selector-healing from config are not applied.

## Config fields used by the bridge

| Field | Purpose |
|-------|---------|
| `conduit_extract_max_chars` | Default max chars for `extract_main` |
| `conduit_crawl_delay_sec` / `conduit_crawl_max_delay_sec` | Crawl rate limiting |
| `selector_healing_enabled` | ARIA/text fallback for click, type, fill, hover |
| `vault` | API keys and credentials (search, login) |
| `searxng_url` / `search_rerank_enabled` | Used by WebSearchTool when registered with config |

## Tool registration

- **Gateway** calls `register_all_tools(loop)` (from `cato.tools`) then `register_all_tools(loop.register_tool, self._cfg)` (from `cato.agent_loop`) so that:
  - Shell, file, memory, and browser (Conduit when enabled) are registered.
  - Web search tools (web.search, web.code, etc.) are registered with **config** so SearXNG, reranking, and vault are used.
- When `conduit_enabled` is true, the browser tool is a `ConduitBrowserTool` that builds the bridge with `cfg.to_conduit_bridge_config(...)` per session.

## Tests

- `tests/test_conduit_config.py` — regression tests for `to_conduit_bridge_config()`, bridge dict config, and tool registration with config.
- `tests/test_audit_chain.py` — all ConduitBridge creation uses the config-dict pattern.
