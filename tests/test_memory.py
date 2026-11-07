import sqlite3

from desktop_agent.agent.memory import RepetitionMemory, SessionContext


def test_session_context_keeps_recent_messages_and_summarizes_old(tmp_path):
    context = SessionContext(max_context_chars=50, keep_recent_messages=2)
    context.add("user", "old question")
    context.add("assistant", "old answer")
    context.add("user", "recent question")
    context.add("assistant", "recent answer")
    calls = []
    result = context.build(lambda transcript: calls.append(transcript) or "summary")
    assert len(calls) == 1
    assert result[0]["role"] == "user"
    assert "reference context" in result[0]["content"]
    assert result[-2]["content"] == "recent question"


def test_context_is_bounded_even_when_latest_message_is_large():
    context = SessionContext(max_context_chars=12, keep_recent_messages=2)
    context.add("user", "first")
    context.add("assistant", "second")
    context.add("user", "this is a very long latest request")
    result = context.build(lambda _: "")
    assert sum(len(item["content"]) for item in result) <= 12
    assert result[-1]["role"] == "user"


def test_repetition_observations_are_not_persisted_before_threshold(tmp_path):
    path = tmp_path / "memory.sqlite3"
    memory = RepetitionMemory(path, repeat_threshold=3)
    assert not memory.observe_success("open-notepad", "Open Notepad for notes")
    assert not memory.observe_success("open-notepad", "Open Notepad for notes")
    assert memory.patterns() == []
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0] == 0
    assert memory.observe_success("open-notepad", "Open Notepad for notes")
    assert memory.patterns() == ["Open Notepad for notes"]


def test_failed_or_unobserved_actions_are_not_learned(tmp_path):
    memory = RepetitionMemory(tmp_path / "memory.sqlite3")
    assert memory.patterns() == []
