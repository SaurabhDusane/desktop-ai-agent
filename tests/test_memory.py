from desktop_agent.agent.memory import RepetitionMemory, SessionContext


def test_session_context_keeps_recent_messages_and_summarizes_old(tmp_path):
    context = SessionContext(max_context_chars=30, keep_recent_messages=2)
    context.add("user", "old question")
    context.add("assistant", "old answer")
    context.add("user", "recent question")
    context.add("assistant", "recent answer")
    calls = []
    result = context.build(lambda transcript: calls.append(transcript) or "summary")
    assert len(calls) == 1
    assert result[0]["role"] == "system"
    assert "summary" in result[0]["content"]
    assert result[-2]["content"] == "recent question"


def test_repetition_memory_promotes_only_after_threshold(tmp_path):
    memory = RepetitionMemory(tmp_path / "memory.sqlite3", repeat_threshold=3)
    assert not memory.observe_success("open-notepad", "Open Notepad for notes")
    assert not memory.observe_success("open-notepad", "Open Notepad for notes")
    assert memory.patterns() == []
    assert memory.observe_success("open-notepad", "Open Notepad for notes")
    assert memory.patterns() == ["Open Notepad for notes"]


def test_failed_or_unobserved_actions_are_not_learned(tmp_path):
    memory = RepetitionMemory(tmp_path / "memory.sqlite3")
    assert memory.patterns() == []
