"""
Logging and metrics tracking for coding-agent skill.
Tracks performance, early termination rate, and model agreement.

Note: logging.basicConfig() is intentionally NOT called here.  Library code
must not configure the root logger; that responsibility belongs to the
application entry point.  Callers that want console output should add a
handler to the root logger or to 'cato' before calling these functions.
"""

import json
import logging
import time
from collections import deque
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# In-memory store for recent invocations (last 100)
_invocation_history: deque = deque(maxlen=100)


class MetricsTracker:
    """Track metrics for coding-agent invocations."""

    def __init__(self) -> None:
        self.invocations: List[Dict] = []
        self.early_terminations: int = 0
        self.total_invocations: int = 0

    def add_invocation(self, invocation: Dict) -> None:
        """
        Add an invocation record.

        Args:
            invocation: Invocation metrics dict.
        """
        self.invocations.append(invocation)
        self.total_invocations += 1

        if invocation.get("terminated_early"):
            self.early_terminations += 1

    def reset(self) -> None:
        """
        Reset all tracked state.

        Useful in tests to prevent cross-test state contamination when the
        module-level singleton is used.
        """
        self.invocations.clear()
        self.early_terminations = 0
        self.total_invocations = 0

    def get_summary(self) -> Dict:
        """
        Return summary statistics over all tracked invocations.

        Returns:
            Dict with keys: total_invocations, early_terminations,
            early_termination_rate, avg_latency_ms, model_win_counts,
            recent_invocations.
        """
        if not self.invocations:
            return {
                "total_invocations": 0,
                "early_terminations": 0,
                "early_termination_rate": 0.0,
                "avg_latency_ms": 0.0,
                "model_win_counts": {},
            }

        latencies = [inv.get("total_latency_ms", 0.0) for inv in self.invocations]
        avg_latency = sum(latencies) / len(latencies)

        model_wins: Dict[str, int] = {}
        for inv in self.invocations:
            winner = inv.get("winner_model", "unknown")
            model_wins[winner] = model_wins.get(winner, 0) + 1

        early_term_rate = (
            self.early_terminations / self.total_invocations * 100
            if self.total_invocations > 0
            else 0.0
        )

        return {
            "total_invocations": self.total_invocations,
            "early_terminations": self.early_terminations,
            "early_termination_rate": early_term_rate,
            "avg_latency_ms": avg_latency,
            "model_win_counts": model_wins,
            "recent_invocations": list(self.invocations[-10:]),
        }


# Module-level singleton
_tracker = MetricsTracker()


def track_invocation(
    task: str,
    total_latency_ms: float,
    winner_model: str,
    winner_confidence: float,
    terminated_early: bool,
    models_responded: int = 3,
    individual_latencies: Optional[Dict[str, float]] = None,
) -> None:
    """
    Record a single invocation in the in-memory history.

    Args:
        task: Task description (truncated to 200 chars in the log line).
        total_latency_ms: Wall-clock time from request start to synthesis.
        winner_model: Which model was selected (claude/codex/gemini).
        winner_confidence: Confidence score of the selected model.
        terminated_early: Whether early termination fired.
        models_responded: Number of models that returned before termination.
        individual_latencies: Mapping of model name to latency_ms.
    """
    individual_latencies = individual_latencies or {}

    invocation: Dict = {
        "timestamp": time.time(),
        "task": task,
        "total_latency_ms": total_latency_ms,
        "winner_model": winner_model,
        "winner_confidence": winner_confidence,
        "terminated_early": terminated_early,
        "models_responded": models_responded,
        "individual_latencies": individual_latencies,
    }

    _invocation_history.append(invocation)
    _tracker.add_invocation(invocation)

    logger.info(
        "Task: %s | Latency: %.1fms | Winner: %s (%.2f) | Early: %s | Models: %d/3",
        task[:50],
        total_latency_ms,
        winner_model,
        winner_confidence,
        terminated_early,
        models_responded,
    )


def get_metrics_summary() -> Dict:
    """
    Return current metrics summary from the module-level tracker.

    Returns:
        Summary dict (see MetricsTracker.get_summary).
    """
    return _tracker.get_summary()


def get_recent_invocations(limit: int = 10) -> List[Dict]:
    """
    Return the most recent invocations from the rolling history.

    Args:
        limit: Maximum number of invocations to return (default 10).

    Returns:
        List of invocation dicts, newest last.
    """
    return list(_invocation_history)[-limit:]


def format_metrics_json() -> str:
    """
    Serialise the current metrics summary as a JSON string.

    Returns:
        Indented JSON string.
    """
    return json.dumps(get_metrics_summary(), indent=2, default=str)


def log_early_termination(model: str, confidence: float, elapsed_ms: float) -> None:
    """
    Emit an INFO log for an early termination event.

    Args:
        model: Model that triggered early termination.
        confidence: Confidence score that exceeded the threshold.
        elapsed_ms: Wall-clock time elapsed before termination fired.
    """
    logger.info(
        "Early termination at %.1fms with %.2f confidence (model: %s)",
        elapsed_ms,
        confidence,
        model,
    )


def log_synthesis_result(
    primary: Dict,
    runner_up_count: int,
    synthesis_note: str,
) -> None:
    """
    Emit an INFO log summarising the synthesis result.

    Args:
        primary: Primary result dict (must contain "model" and "confidence").
        runner_up_count: Number of runner-up alternatives.
        synthesis_note: Human-readable explanation of the selection.
    """
    logger.info(
        "Synthesis complete: %s | Runner-ups: %d",
        synthesis_note,
        runner_up_count,
    )


def reset_metrics() -> None:
    """
    Reset the module-level tracker and history.

    Intended for use in tests to prevent cross-test state contamination.
    """
    global _invocation_history
    _invocation_history.clear()
    _tracker.reset()
