import pytest

from desktop_agent.agent.safe_paths import PathAccessError, SafePathPolicy


def test_path_inside_allowed_root_is_accepted(tmp_path):
    allowed = tmp_path / "workspace"
    allowed.mkdir()
    policy = SafePathPolicy([allowed])
    assert policy.resolve(allowed / "notes.txt") == (allowed / "notes.txt").resolve()


def test_path_outside_allowed_root_is_rejected(tmp_path):
    allowed = tmp_path / "workspace"
    allowed.mkdir()
    outside = tmp_path / "private.txt"
    policy = SafePathPolicy([allowed])
    with pytest.raises(PathAccessError):
        policy.resolve(outside)


def test_blocked_subfolder_is_rejected(tmp_path):
    allowed = tmp_path / "workspace"
    protected = allowed / "secrets"
    protected.mkdir(parents=True)
    policy = SafePathPolicy([allowed], [protected])
    with pytest.raises(PathAccessError):
        policy.resolve(protected / "key.txt")
