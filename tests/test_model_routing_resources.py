from desktop_agent.agent.model_router import (
    ModelBenchmarkStore, ModelProfile, ModelRouter, profile_from_ollama,
)
from desktop_agent.agent.resources import InferenceBudget, ResourceBudgetManager, ResourceSnapshot


def test_router_prefers_measured_quality_and_speed():
    router = ModelRouter()
    router.update_profiles([
        ModelProfile("slow", benchmark_latency_ms=9000, benchmark_quality=0.8),
        ModelProfile("fast", benchmark_latency_ms=800, benchmark_quality=0.85),
    ])
    decision = router.choose(["slow", "fast"])
    assert decision.model == "fast"
    assert decision.measured


def test_router_respects_context_and_capability_constraints():
    router = ModelRouter()
    router.update_profiles([
        ModelProfile("small", context_length=4096, capabilities=frozenset({"chat"})),
        ModelProfile("tool", context_length=16384, capabilities=frozenset({"chat", "tools"})),
    ])
    assert router.choose(["small", "tool"], task="tools", required_context=8192).model == "tool"


def test_explicit_selection_is_respected():
    router = ModelRouter()
    router.update_profiles([ModelProfile("a"), ModelProfile("b")])
    assert router.choose(["a", "b"], preferred="b").model == "b"


def test_router_fallback_when_no_candidate_meets_constraints():
    router = ModelRouter()
    router.update_profiles([ModelProfile("chat", capabilities=frozenset({"chat"}))])
    decision = router.choose(["chat"], task="vision")
    assert decision.model == "chat"
    assert decision.score == 0


def test_benchmark_store_persists_only_measurements(tmp_path):
    store = ModelBenchmarkStore(tmp_path / "benchmarks.sqlite3")
    store.record("local-model", 1200, 0.9)
    router = ModelRouter(store)
    router.update_profiles([ModelProfile("local-model", context_length=8192)])
    profile = router.profiles()[0]
    assert profile.benchmark_latency_ms == 1200
    assert profile.benchmark_quality == 0.9
    assert profile.source == "local_benchmark"


def test_ollama_metadata_normalization():
    profile = profile_from_ollama(
        "local:latest",
        {"capabilities": ["completion", "tools", "vision"],
         "model_info": {"llama.context_length": 32768},
         "details": {"parameter_size": "8B"}},
        [{"name": "local:latest", "size_vram": 7_000_000_000}],
    )
    assert profile.context_length == 32768
    assert profile.capabilities == frozenset({"chat", "code", "tools", "vision"})
    assert profile.estimated_vram_bytes == 7_000_000_000


def test_resource_budget_reduces_context_under_memory_pressure():
    snapshot = ResourceSnapshot(1, 16 * 1024**3, 5 * 1024**3,
                                500 * 1024**3, 200 * 1024**3)
    budget = ResourceBudgetManager().budget(snapshot, requested_context=32768,
                                             requested_parallel=3)
    assert budget.max_context_tokens == 8192
    assert budget.max_parallel_requests == 1
    assert budget.warnings


def test_resource_budget_warns_when_model_exceeds_free_vram():
    snapshot = ResourceSnapshot(1, 32 * 1024**3, 20 * 1024**3,
                                500 * 1024**3, 200 * 1024**3,
                                "GPU", 16 * 1024**3, 2 * 1024**3, "nvidia-smi")
    budget = ResourceBudgetManager().budget(snapshot, estimated_model_memory_bytes=4 * 1024**3)
    assert budget.max_parallel_requests == 1
    assert any("VRAM" in warning for warning in budget.warnings)
