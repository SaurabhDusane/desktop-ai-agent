import pytest

from desktop_agent.desktop.environment import EnvironmentStateGraph, EnvironmentStateService


def windows():
    return [
        {"title": "Editor - project.py", "process_id": 100, "handle": 10,
         "control_type": "Window"},
        {"title": "Browser", "process_id": 200, "handle": 20,
         "control_type": "Window"},
        {"title": "Terminal", "process_id": 100, "handle": 11,
         "control_type": "Window"},
    ]


def test_graph_builds_application_window_relationships():
    graph = EnvironmentStateGraph()
    result = graph.replace_windows(windows())
    assert result["stale"] is False
    assert result["node_count"] == 6
    assert result["edge_count"] == 5
    assert len([node for node in result["nodes"] if node["kind"] == "application"]) == 2
    assert len([node for node in result["nodes"] if node["kind"] == "window"]) == 3


def test_graph_query_filters_by_text_and_kind():
    graph = EnvironmentStateGraph()
    graph.replace_windows(windows())
    result = graph.query("browser", kind="window")
    assert len(result["matches"]) == 1
    assert result["matches"][0]["label"] == "Browser"


def test_graph_is_bounded_and_rejects_invalid_limits():
    graph = EnvironmentStateGraph(max_nodes=3)
    with pytest.raises(ValueError, match="node budget"):
        graph.replace_windows(windows())
    with pytest.raises(ValueError, match="limit"):
        graph.snapshot(limit=0)
    with pytest.raises(ValueError, match="bound"):
        graph.query("x", limit=201)


def test_graph_replaces_old_observations_instead_of_accumulating():
    graph = EnvironmentStateGraph()
    graph.replace_windows(windows())
    result = graph.replace_windows([windows()[0]])
    assert result["node_count"] == 3
    assert result["edge_count"] == 2
    assert result["generation"] == 2


def test_refresh_uses_injected_observer_and_fails_when_unavailable():
    graph = EnvironmentStateGraph()
    service = EnvironmentStateService(graph, lambda: windows())
    assert service.refresh_desktop()["node_count"] == 6
    unavailable = EnvironmentStateService(EnvironmentStateGraph())
    with pytest.raises(RuntimeError, match="unavailable"):
        unavailable.refresh_desktop()


def test_malformed_window_records_are_ignored():
    graph = EnvironmentStateGraph()
    result = graph.replace_windows([{"title": "missing pid"}, None])
    assert result["node_count"] == 1
    assert result["edge_count"] == 0


def test_environment_tools_are_registered_through_central_registry(tmp_path):
    from desktop_agent.agent.audit import AuditLog
    from desktop_agent.agent.models import ToolCall
    from desktop_agent.agent.policy import PermissionPolicy
    from desktop_agent.agent.registry import ToolRegistry
    from desktop_agent.desktop.environment_tools import register_environment_tools

    graph = EnvironmentStateGraph()
    service = EnvironmentStateService(graph, lambda: windows())
    registry = ToolRegistry(PermissionPolicy(), AuditLog(tmp_path / "audit.db"))
    register_environment_tools(registry, service)

    refreshed = registry.execute(ToolCall("environment_refresh_desktop"))
    assert refreshed["node_count"] == 6
    snapshot = registry.execute(ToolCall(
        "environment_snapshot", {"kind": "window", "limit": 10}
    ))
    assert len(snapshot["nodes"]) == 3
    query = registry.execute(ToolCall(
        "environment_query", {"text": "editor", "kind": "window"}
    ))
    assert len(query["matches"]) == 1
