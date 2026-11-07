"""Capability-aware local model selection backed by measured benchmark profiles."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Callable, Iterable


@dataclass(frozen=True, slots=True)
class ModelProfile:
    name: str
    parameter_size: str = ""
    context_length: int | None = None
    capabilities: frozenset[str] = frozenset({"chat"})
    benchmark_latency_ms: float | None = None
    benchmark_quality: float | None = None
    estimated_vram_bytes: int | None = None
    source: str = "ollama_metadata"


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    model: str
    reason: str
    score: float
    measured: bool


class ModelRouter:
    """Ranks installed models; never pulls, starts, or changes a model implicitly."""

    def __init__(self) -> None:
        self._profiles: dict[str, ModelProfile] = {}

    def update_profiles(self, profiles: Iterable[ModelProfile]) -> None:
        self._profiles = {profile.name: profile for profile in profiles if profile.name}

    def record_benchmark(self, model: str, latency_ms: float, quality: float) -> None:
        if latency_ms <= 0 or not math.isfinite(latency_ms) or not 0 <= quality <= 1:
            raise ValueError("Benchmark latency must be positive and quality must be between 0 and 1.")
        old = self._profiles.get(model, ModelProfile(model))
        self._profiles[model] = ModelProfile(
            old.name, old.parameter_size, old.context_length, old.capabilities,
            latency_ms, quality, old.estimated_vram_bytes, "local_benchmark",
        )

    def profiles(self) -> tuple[ModelProfile, ...]:
        return tuple(self._profiles[name] for name in sorted(self._profiles))

    def choose(
        self, installed: Iterable[str], task: str = "general",
        required_context: int = 0, available_vram_bytes: int | None = None,
        preferred: str | None = None,
    ) -> RoutingDecision:
        names = list(dict.fromkeys(installed))
        if preferred and preferred in names:
            return RoutingDecision(preferred, "Explicit model selection", 1.0, False)
        candidates: list[tuple[float, ModelProfile]] = []
        capability = {"code": "code", "vision": "vision", "tools": "tools"}.get(task, "chat")
        for name in names:
            profile = self._profiles.get(name, ModelProfile(name))
            if capability not in profile.capabilities and capability != "chat":
                continue
            if profile.context_length is not None and required_context > profile.context_length:
                continue
            if (available_vram_bytes is not None and profile.estimated_vram_bytes is not None
                    and profile.estimated_vram_bytes > available_vram_bytes):
                continue
            quality = profile.benchmark_quality if profile.benchmark_quality is not None else 0.5
            latency = profile.benchmark_latency_ms
            speed = 0.5 if latency is None else 1.0 / (1.0 + latency / 5000.0)
            measured_bonus = 0.05 if profile.source == "local_benchmark" else 0.0
            candidates.append((quality * 0.65 + speed * 0.30 + measured_bonus, profile))
        if not candidates:
            if not names:
                raise ValueError("No local Ollama models are installed.")
            # Safe fallback: keep the current installed model; do not infer capability.
            name = preferred if preferred in names else names[0]
            return RoutingDecision(name, "Fallback: no profile satisfied task constraints", 0.0, False)
        score, profile = max(candidates, key=lambda item: (item[0], item[1].name))
        measured = profile.benchmark_latency_ms is not None
        reason = "Best measured local profile" if measured else "Metadata-based provisional ranking; benchmark recommended"
        return RoutingDecision(profile.name, reason, score, measured)


def benchmark_model(model: str, invoke: Callable[[str], str], prompt: str) -> tuple[float, str]:
    """Measure one local inference request; caller evaluates answer quality separately."""
    started = time.perf_counter()
    answer = invoke(model)
    elapsed = (time.perf_counter() - started) * 1000
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Benchmark produced an empty model response.")
    return elapsed, answer
