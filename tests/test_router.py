from __future__ import annotations

from cato.router import ModelRouter


class DummyVault:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str) -> str:
        return self._values.get(key, "")


def test_human_minimax_label_maps_to_openrouter_slug() -> None:
    vault = DummyVault({"OPENROUTER_API_KEY": "test-openrouter"})
    router = ModelRouter(vault=vault, preferred_model="Minimax:MiniMax M2.5")
    assert router.select_model(0.0) == "openrouter/minimax/minimax-m2.5"


def test_low_complexity_fallback_skips_claude_without_anthropic_key() -> None:
    vault = DummyVault({"GOOGLE_API_KEY": "test-google"})
    router = ModelRouter(vault=vault, preferred_model="")
    assert router.select_model(0.0) == "gemini-2.0-flash-lite"
