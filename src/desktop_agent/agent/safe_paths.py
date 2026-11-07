"""Path boundary helpers for future file tools.

Call these helpers at the tool boundary; never rely on model-provided paths directly.
"""

from pathlib import Path


class PathAccessError(PermissionError):
    """Raised when a path escapes the configured filesystem boundary."""


class SafePathPolicy:
    def __init__(self, allowed_roots: list[str | Path], blocked_roots: list[str | Path] | None = None):
        if not allowed_roots:
            raise ValueError("At least one allowed root is required")
        self.allowed_roots = tuple(Path(root).expanduser().resolve() for root in allowed_roots)
        self.blocked_roots = tuple(Path(root).expanduser().resolve() for root in (blocked_roots or []))

    @staticmethod
    def _within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def resolve(self, candidate: str | Path, *, must_exist: bool = False) -> Path:
        raw = Path(candidate).expanduser()
        # Resolve existing symlinks/junctions in the path before checking boundaries.
        resolved = raw.resolve(strict=must_exist)
        if not any(self._within(resolved, root) for root in self.allowed_roots):
            raise PathAccessError("Path is outside the configured allowed folders.")
        if any(self._within(resolved, root) for root in self.blocked_roots):
            raise PathAccessError("Path is inside a protected folder.")
        return resolved
