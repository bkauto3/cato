"""
cato/router.py — SwarmSync-aware model router for CATO.

Routes tasks to the optimal LLM based on complexity scoring.
When SwarmSync API key is present, delegates to the SwarmSync API.
Supports Anthropic, OpenAI-compatible, and Google streaming APIs.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model translation: OpenRouter slugs → native IDs
# ---------------------------------------------------------------------------

MODEL_TRANSLATIONS: dict[str, str] = {
    "anthropic/claude-opus-4-6":     "claude-opus-4-6",
    "anthropic/claude-sonnet-4-6":   "claude-sonnet-4-6",
    "anthropic/claude-haiku-4-5":    "claude-haiku-4-5-20251001",
    "openai/gpt-4o":                 "gpt-4o",
    "openai/gpt-4o-mini":            "gpt-4o-mini",
    "openai/o3-mini":                "o3-mini",
    "google/gemini-2.0-pro":         "gemini-2.0-pro-exp",
    "google/gemini-2.0-flash":       "gemini-2.0-flash",
    "google/gemini-2.0-flash-lite":  "gemini-2.0-flash-lite",
    "deepseek/deepseek-v3":          "deepseek-chat",
    "deepseek/deepseek-r1":          "deepseek-reasoner",
    "groq/llama-3.3-70b":            "llama-3.3-70b-versatile",
    "mistral/mistral-small":         "mistral-small-latest",
    "minimax/minimax-2.5":           "abab7-chat-preview",
    "minimax/minimax-m2.5":          "abab7-chat-preview",
    "Minimax:MiniMax M2.5":          "openrouter/minimax/minimax-m2.5",
    "openrouter/minimax/minimax-2.5":  "abab7-chat-preview",
    "openrouter/minimax/minimax-m2.5": "abab7-chat-preview",
    "moonshot/kimi-k2.5":            "moonshot-v1-8k",
}

_ECONOMY = ["claude-haiku-4-5-20251001", "gemini-2.0-flash-lite", "llama-3.3-70b-versatile"]
_MID     = ["claude-sonnet-4-6", "gemini-2.0-flash", "gpt-4o-mini", "deepseek-chat"]
_PREMIUM = ["claude-opus-4-6", "gemini-2.0-pro-exp", "gpt-4o", "deepseek-reasoner"]

# (prefix, base_url, auth_scheme)
_PROVIDERS: list[tuple[str, str, str]] = [
    ("claude-",     "https://api.anthropic.com/v1/messages",                                    "x-api-key"),
    ("gpt-",        "https://api.openai.com/v1/chat/completions",                               "bearer"),
    ("o3-",         "https://api.openai.com/v1/chat/completions",                               "bearer"),
    ("gemini-",     "https://generativelanguage.googleapis.com/v1beta/models",                  "google"),
    ("deepseek-",   "https://api.deepseek.com/v1/chat/completions",                             "bearer"),
    ("llama-",      "https://api.groq.com/openai/v1/chat/completions",                          "bearer"),
    ("mistral-",    "https://api.mistral.ai/v1/chat/completions",                               "bearer"),
    ("abab",        "https://api.minimax.chat/v1/text/chatcompletion_pro",                      "bearer"),
    ("moonshot-",   "https://api.moonshot.cn/v1/chat/completions",                              "bearer"),
    ("openrouter/", "https://openrouter.ai/api/v1/chat/completions",                            "openrouter"),
]

def _is_model_slug_only(text: str) -> bool:
    """True if text looks like a model id (e.g. openrouter/minimax/minimax-m2.5) and nothing else.
    Some providers echo the model in stream content; we skip it so the UI doesn't show only the model name.
    """
    t = (text or "").strip()
    if not t or len(t) > 120:
        return False
    # Model slugs: openrouter/..., provider/name, or single-word model ids
    if t.startswith("openrouter/") or "/" in t and re.match(r"^[\w\-./]+$", t):
        return True
    return False


# Signal regexes for complexity scoring
_RE_REASON   = re.compile(r"\b(why|analyze|analyse|compare|explain|evaluate|assess)\b", re.I)
_RE_MATH     = re.compile(r"\b(calculate|compute|proof|prove|solve|integral|derivative)\b", re.I)
_RE_MULTI    = re.compile(r"\b(then|after that|first[,\s]|second[,\s]|finally|step \d)\b", re.I)
_RE_CREATIVE = re.compile(r"\b(write|generate|create|compose|draft)\b", re.I)
_RE_CODE     = re.compile(r"(```|def |class |import |#include|function\s+\w+)", re.I)
_RE_NONENGL  = re.compile(r"[^\x00-\x7F]")


class ModelRouter:
    """Routes tasks to optimal model via local scoring or SwarmSync API."""

    def __init__(
        self,
        vault: Any,
        preferred_model: str = "claude-sonnet-4-6",
        blocked_models: Optional[list[str]] = None,
        swarmsync_api_url: str = "https://api.swarmsync.ai/v1/chat/completions",
    ) -> None:
        self._vault = vault
        # Keep openrouter/ prefixed models untranslated so they route through
        # the OpenRouter provider entry.  All other slugs are translated to their
        # native IDs (e.g. "anthropic/claude-sonnet-4-6" → "claude-sonnet-4-6").
        if preferred_model.startswith("openrouter/"):
            self._preferred = preferred_model
        else:
            self._preferred = MODEL_TRANSLATIONS.get(preferred_model, preferred_model)
        self._blocked: set[str] = set(blocked_models or [])
        self._swarmsync_url = swarmsync_api_url

    def score_task(self, message: str, context_tokens: int, history_len: int) -> float:
        """Return 0.0-1.0 complexity score from message signals."""
        s = 0.0
        if len(message) > 500:       s += 0.10
        if _RE_CODE.search(message):     s += 0.15
        if _RE_REASON.search(message):   s += 0.10
        if _RE_MATH.search(message):     s += 0.15
        if context_tokens > 4000:    s += 0.10
        if _RE_MULTI.search(message):    s += 0.10
        if _RE_CREATIVE.search(message): s += 0.05
        if _RE_NONENGL.search(message):  s += 0.10
        if history_len > 10:         s += 0.05
        return min(1.0, round(s, 4))

    def select_model(self, score: float, task_type: Optional[str] = None) -> str:
        """Return native model ID for score band, respecting blocked/preferred config."""
        # Always honour preferred_model if set and not blocked — even if it's an
        # openrouter/ or other external model not in the local pool lists.
        if self._preferred and self._is_available(self._preferred):
            return self._preferred
        pool = _ECONOMY if score < 0.35 else (_MID if score < 0.70 else _PREMIUM)
        for m in pool:
            if self._is_available(m):
                return m
        if self._preferred and self._preferred not in self._blocked:
            return self._preferred
        for m in _ECONOMY + _MID + _PREMIUM:
            if self._is_available(m):
                return m
        return _ECONOMY[0]  # last-resort: cheapest available model

    async def _swarmsync_route(
        self, messages: list[dict], api_key: str, score: float
    ) -> str:
        """
        Query SwarmSync API and return the routed model name.

        SwarmSync always executes the completion regardless of ``routing_only``
        flag.  Use :meth:`_swarmsync_complete` when you want the completion
        text directly (avoids a second API call).  This method discards the
        completion body and only returns the model that was chosen.

        Falls back to local selection on any error.
        """
        result = await self._swarmsync_complete(messages, api_key, score)
        return result[0]  # (model, text) — caller only wants model here

    async def _swarmsync_complete(
        self, messages: list[dict], api_key: str, score: float
    ) -> tuple[str, str]:
        """
        Call SwarmSync and return ``(routed_model, completion_text)``.

        SwarmSync always runs a full completion regardless of ``routing_only``.
        The system prompt and skills travel in ``messages``, so the model
        receives full context.  We use the response text directly to avoid
        paying twice for the same call.

        Returns ``(select_model(score), "")`` on any error so callers can fall
        back gracefully.
        """
        payload = {
            "model": "auto",
            "messages": messages,
            "stream": False,
            "swarmsync": {
                "complexity_score": score,
                "history_length": len(messages),
            },
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    self._swarmsync_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as r:
                    # SwarmSync returns 200 or 201 depending on version
                    if r.status in (200, 201):
                        data = await r.json()
                        # Extract routed model name
                        raw_model = (
                            data.get("swarmsync", {}).get("routed_model", "")
                            or data.get("model", "")
                        )
                        model = self.select_model(score)  # fallback
                        if raw_model and raw_model != "auto":
                            model = self._resolve_swarmsync_model(raw_model, score)
                            logger.info("SwarmSync routed to: %s (raw: %s)", model, raw_model)
                        # Extract completion text from choices
                        text = ""
                        choices = data.get("choices", [])
                        if choices:
                            text = choices[0].get("message", {}).get("content", "") or ""
                        return model, text
                    else:
                        body = await r.text()
                        logger.warning("SwarmSync HTTP %d: %s", r.status, body[:200])
        except Exception as exc:
            logger.warning("SwarmSync completion failed: %s — using local selection", exc)
        return self.select_model(score), ""

    def _resolve_swarmsync_model(self, raw_model: str, score: float) -> str:
        """
        Convert a SwarmSync-recommended model slug to a locally-usable model ID.

        Strategy (in order):
          1. Direct translation table hit → use native ID
          2. Model already has a native API key → use as-is
          3. OpenRouter key available → prefix with ``openrouter/`` and route
             through OpenRouter (strips leading ``openrouter/`` if already present
             to avoid double-prefix)
          4. Fall back to local score-based selection
        """
        # 1. Check explicit translation table
        if raw_model in MODEL_TRANSLATIONS:
            translated = MODEL_TRANSLATIONS[raw_model]
            if self._is_available(translated):
                return translated

        # 2. Check if raw model is directly usable (native key exists)
        if self._is_available(raw_model):
            return raw_model

        # 3. Route through OpenRouter if we have a key
        openrouter_key = self._vault.get("OPENROUTER_API_KEY")
        if openrouter_key:
            # Avoid double-prefix: openrouter/openrouter/... is invalid
            clean = raw_model.removeprefix("openrouter/")
            as_openrouter = f"openrouter/{clean}"
            return as_openrouter

        # 4. Fall back to local score-based selection
        logger.warning(
            "SwarmSync recommended %r but no suitable API key found — using local selection",
            raw_model,
        )
        return self.select_model(score)

    async def complete(
        self,
        messages: list[dict],
        model: str,
        tools: Optional[list[dict]] = None,
        stream: bool = True,
    ) -> AsyncIterator[str]:
        """Stream completions from the provider matched to *model*."""
        base_url, auth = self._resolve_provider(model)
        api_key = self._get_api_key(auth, model)
        if auth == "x-api-key":
            async for c in self._anthropic(messages, model, tools or [], api_key):
                yield c
        elif auth == "google":
            async for c in self._google(messages, model, api_key):
                yield c
        else:
            async for c in self._openai_compat(messages, model, tools or [], api_key, base_url):
                yield c

    # ------------------------------------------------------------------
    # Provider implementations
    # ------------------------------------------------------------------

    async def _anthropic(self, messages: list[dict], model: str,
                          tools: list[dict], api_key: str) -> AsyncIterator[str]:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        payload: dict[str, Any] = {"model": model, "max_tokens": 4096,
                                   "messages": user_msgs, "stream": True}
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.post("https://api.anthropic.com/v1/messages",
                              json=payload, headers=headers) as r:
                r.raise_for_status()
                async for line in r.content:
                    decoded = line.decode("utf-8").strip()
                    if not decoded.startswith("data: "):
                        continue
                    raw = decoded[6:]
                    if raw == "[DONE]":
                        break
                    try:
                        d = json.loads(raw).get("delta", {})
                        if d.get("type") == "text_delta":
                            yield d.get("text", "")
                    except json.JSONDecodeError:
                        pass

    async def _openai_compat(self, messages: list[dict], model: str, tools: list[dict],
                              api_key: str, base_url: str) -> AsyncIterator[str]:
        # OpenRouter expects "provider/model" not "openrouter/provider/model"
        api_model = model.removeprefix("openrouter/") if model.startswith("openrouter/") else model
        payload: dict[str, Any] = {"model": api_model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.post(base_url, json=payload, headers=headers) as r:
                r.raise_for_status()
                async for line in r.content:
                    decoded = line.decode("utf-8").strip()
                    if not decoded.startswith("data: "):
                        continue
                    raw = decoded[6:]
                    if raw == "[DONE]":
                        break
                    try:
                        choice = json.loads(raw)["choices"][0]
                        delta = choice.get("delta", {})
                        finish = choice.get("finish_reason")
                        content = delta.get("content")
                        if content and not _is_model_slug_only(content):
                            yield content
                        elif finish == "tool_calls" and not content:
                            # Model responded with a tool-call frame but no prose
                            # (e.g. MiniMax M2.5 hallucinates function calls).
                            # Surface the tool name as a text hint so the response
                            # is never silently empty.
                            tool_calls = delta.get("tool_calls") or []
                            if tool_calls:
                                names = ", ".join(
                                    tc.get("function", {}).get("name", "unknown")
                                    for tc in tool_calls
                                )
                                yield f"[attempted tool call: {names} — please rephrase your request]"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass

    async def _google(self, messages: list[dict], model: str,
                       api_key: str) -> AsyncIterator[str]:
        contents: list[dict] = []
        sys_parts: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                sys_parts.append({"text": m["content"]})
                continue
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        payload: dict[str, Any] = {"contents": contents}
        if sys_parts:
            payload["system_instruction"] = {"parts": sys_parts}
        url = (f"https://generativelanguage.googleapis.com/v1beta/models"
               f"/{model}:streamGenerateContent")
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.post(url, json=payload, headers=headers) as r:
                r.raise_for_status()
                try:
                    events = json.loads(await r.text())
                    if not isinstance(events, list):
                        events = [events]
                    for evt in events:
                        for cand in evt.get("candidates", []):
                            for part in cand.get("content", {}).get("parts", []):
                                if "text" in part:
                                    yield part["text"]
                except (json.JSONDecodeError, KeyError):
                    pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_provider(self, model: str) -> tuple[str, str]:
        for prefix, url, auth in _PROVIDERS:
            if model.startswith(prefix):
                return url, auth
        return "https://api.openai.com/v1/chat/completions", "bearer"

    def _is_available(self, model: str) -> bool:
        resolved = MODEL_TRANSLATIONS.get(model, model)
        if resolved in self._blocked or model in self._blocked:
            return False
        _, auth = self._resolve_provider(resolved)
        api_key = self._get_api_key(auth, resolved)
        return bool(api_key)

    def _get_api_key(self, auth: str, model: str) -> str:
        if auth == "x-api-key":
            return self._vault.get("ANTHROPIC_API_KEY") or ""
        if auth == "google":
            return self._vault.get("GOOGLE_API_KEY") or ""
        if auth == "openrouter":
            return self._vault.get("OPENROUTER_API_KEY") or ""
        mapping = {
            "openrouter/": "OPENROUTER_API_KEY",
            "swarmsync/":  "SWARMSYNC_API_KEY",
            "deepseek-":   "DEEPSEEK_API_KEY",
            "llama-":      "GROQ_API_KEY",
            "mistral-":    "MISTRAL_API_KEY",
            "abab":        "MINIMAX_API_KEY",
            "moonshot-":   "MOONSHOT_API_KEY",
        }
        for prefix, vault_key in mapping.items():
            if model.startswith(prefix):
                return self._vault.get(vault_key) or ""
        return self._vault.get("OPENAI_API_KEY") or ""
