"""Capability-based authorization independent of tool risk classification."""

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True, slots=True)
class Capability:
    resource: str
    actions: frozenset[str]
    scope: str = "*"

    def __post_init__(self) -> None:
        if not self.resource.strip() or not self.actions or any(not a.strip() for a in self.actions):
            raise ValueError("A capability needs a resource and at least one action.")
        if not self.scope.strip():
            raise ValueError("Capability scope cannot be empty.")

    def covers(self, required: "Capability") -> bool:
        resource_matches = self.resource == required.resource or self.resource == "*"
        scope_matches = self.scope == "*" or self.scope == required.scope
        return resource_matches and scope_matches and required.actions.issubset(self.actions)


class CapabilityPolicy:
    """In-memory grants only; revocations override both baseline and session grants."""

    def __init__(self, baseline: tuple[Capability, ...] = ()) -> None:
        self._baseline = tuple(baseline)
        self._grants: set[Capability] = set()
        self._revoked: set[Capability] = set()
        self._lock = RLock()

    def missing(self, required: tuple[Capability, ...]) -> tuple[Capability, ...]:
        with self._lock:
            available = tuple(
                grant for grant in self._baseline + tuple(self._grants)
                if grant not in self._revoked
            )
            return tuple(
                need for need in required
                if not any(grant.covers(need) for grant in available)
            )

    def grant(self, capability: Capability) -> None:
        with self._lock:
            self._revoked.discard(capability)
            self._grants.add(capability)

    def revoke(self, capability: Capability) -> None:
        with self._lock:
            self._grants.discard(capability)
            self._revoked.add(capability)

    def revoke_all(self) -> None:
        with self._lock:
            self._grants.clear()
            self._revoked.update(self._baseline)

    def grants(self) -> tuple[Capability, ...]:
        with self._lock:
            return tuple(sorted(
                (item for item in self._grants if item not in self._revoked),
                key=lambda item: (item.resource, item.scope, sorted(item.actions)),
            ))
