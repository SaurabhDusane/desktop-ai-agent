"""Bounded, session-local graph of observed desktop environment metadata.

No screenshots, document contents, control values, or continuous monitoring are stored.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class EnvironmentNode:
    node_id: str
    kind: str
    label: str
    attributes: dict[str, Any]
    source: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class EnvironmentEdge:
    source_id: str
    relation: str
    target_id: str


class EnvironmentStateGraph:
    """In-memory graph with hard bounds and explicit freshness metadata."""

    def __init__(
        self,
        max_nodes: int = 500,
        max_edges: int = 1000,
        stale_after_seconds: int = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_nodes < 1 or max_edges < 0 or stale_after_seconds < 1:
            raise ValueError("Graph bounds and freshness interval must be positive.")
        self.max_nodes = max_nodes
        self.max_edges = max_edges
        self.stale_after_seconds = stale_after_seconds
        self._clock = clock
        self._nodes: dict[str, EnvironmentNode] = {}
        self._edges: list[EnvironmentEdge] = []
        self._last_refresh: float | None = None
        self._last_refresh_iso: str | None = None
        self._generation = 0

    @property
    def is_stale(self) -> bool:
        return (
            self._last_refresh is None
            or self._clock() - self._last_refresh > self.stale_after_seconds
        )

    def replace_windows(self, windows: list[dict[str, Any]]) -> dict[str, Any]:
        """Replace the observed desktop slice; reject malformed/unbounded input."""
        if not isinstance(windows, list):
            raise ValueError("Window observations must be a list.")
        if len(windows) > min(self.max_nodes - 1, 200):
            raise ValueError("Window observation exceeds the graph node budget.")

        now = datetime.now(timezone.utc).isoformat()
        nodes: dict[str, EnvironmentNode] = {}
        edges: list[EnvironmentEdge] = []
        workspace_id = "workspace:current"
        nodes[workspace_id] = EnvironmentNode(
            workspace_id, "workspace", "Current desktop", {},
            "windows_ui_automation", now,
        )

        for item in windows:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            pid = item.get("process_id")
            handle = item.get("handle")
            if not isinstance(title, str) or not isinstance(pid, int) or not isinstance(handle, int):
                continue
            title = title[:200]
            if pid < 0 or handle < 0:
                continue
            app_id = f"application:{pid}"
            window_id = f"window:{pid}:{handle}"
            if app_id not in nodes:
                nodes[app_id] = EnvironmentNode(
                    app_id, "application", f"Process {pid}",
                    {"process_id": pid}, "windows_ui_automation", now,
                )
                edges.append(EnvironmentEdge(workspace_id, "contains", app_id))
            nodes[window_id] = EnvironmentNode(
                window_id, "window", title,
                {
                    "title": title,
                    "process_id": pid,
                    "handle": handle,
                    "control_type": str(item.get("control_type") or "Window")[:60],
                    "visible": True,
                },
                "windows_ui_automation", now,
            )
            edges.append(EnvironmentEdge(app_id, "owns_window", window_id))

        if len(nodes) > self.max_nodes or len(edges) > self.max_edges:
            raise ValueError("Observed desktop state exceeds configured graph bounds.")
        self._nodes = nodes
        self._edges = edges
        self._last_refresh = self._clock()
        self._last_refresh_iso = now
        self._generation += 1
        return self.snapshot()

    def snapshot(self, kind: str = "", limit: int = 100) -> dict[str, Any]:
        if not 1 <= limit <= 200:
            raise ValueError("Snapshot limit must be between 1 and 200.")
        selected = [
            node for node in self._nodes.values()
            if not kind or node.kind == kind
        ][:limit]
        ids = {node.node_id for node in selected}
        edges = [
            edge for edge in self._edges
            if edge.source_id in ids and edge.target_id in ids
        ][: self.max_edges]
        return {
            "generation": self._generation,
            "stale": self.is_stale,
            "last_refresh": self._last_refresh_iso,
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "nodes": [
                {
                    "id": node.node_id, "kind": node.kind, "label": node.label,
                    "attributes": dict(node.attributes), "source": node.source,
                    "observed_at": node.observed_at,
                }
                for node in selected
            ],
            "edges": [
                {"source": edge.source_id, "relation": edge.relation, "target": edge.target_id}
                for edge in edges
            ],
        }

    def query(self, text: str = "", kind: str = "", limit: int = 50) -> dict[str, Any]:
        if len(text) > 200 or not 1 <= limit <= 200:
            raise ValueError("Query text or result limit exceeds its bound.")
        needle = text.casefold().strip()
        matches = []
        for node in self._nodes.values():
            if kind and node.kind != kind:
                continue
            searchable = " ".join(
                [node.label, node.kind, *(str(value) for value in node.attributes.values())]
            ).casefold()
            if needle and needle not in searchable:
                continue
            matches.append(node)
            if len(matches) >= limit:
                break
        ids = {node.node_id for node in matches}
        return {
            "generation": self._generation,
            "stale": self.is_stale,
            "last_refresh": self._last_refresh_iso,
            "matches": [
                {
                    "id": node.node_id, "kind": node.kind, "label": node.label,
                    "attributes": dict(node.attributes), "source": node.source,
                    "observed_at": node.observed_at,
                }
                for node in matches
            ],
            "edges": [
                {"source": edge.source_id, "relation": edge.relation, "target": edge.target_id}
                for edge in self._edges
                if edge.source_id in ids or edge.target_id in ids
            ][: self.max_edges],
        }


class EnvironmentStateService:
    """Refresh and query the graph using a caller-supplied authorized observation."""

    def __init__(
        self,
        graph: EnvironmentStateGraph,
        window_observer: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.graph = graph
        self.window_observer = window_observer

    def refresh_desktop(self) -> dict[str, Any]:
        if self.window_observer is None:
            raise RuntimeError("Desktop observation is unavailable on this platform.")
        windows = self.window_observer()
        return self.graph.replace_windows(windows)
