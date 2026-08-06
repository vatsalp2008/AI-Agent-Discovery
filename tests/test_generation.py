"""The summary step must never be able to break a search."""

import pytest

import config
import generation


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeChat:
    """Stands in for ChatOllama, recording the messages it was given."""

    def __init__(self, content="Cursor suits a full editor workflow.", error=None):
        self.content = content
        self.error = error
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return FakeResponse(self.content)


@pytest.fixture
def results():
    return [
        {
            "name": "Cursor",
            "description": "AI-powered code editor.",
            "metadata": {
                "name": "Cursor", "category": "Code Generation",
                "stack": "Electron,GPT-4", "description": "AI-powered code editor.",
            },
        },
        {
            "name": "Aider",
            "description": "Pair program from the terminal.",
            "metadata": {
                "name": "Aider", "category": "Code Generation",
                "stack": "Python,Git", "description": "Pair program from the terminal.",
            },
        },
    ]


@pytest.fixture(autouse=True)
def summaries_enabled(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_SUMMARY", True)


def test_returns_the_generated_text(results):
    chat = FakeChat("Cursor is a full editor; Aider works in the terminal.")
    assert generation.summarize("code editor", results, client=chat) == (
        "Cursor is a full editor; Aider works in the terminal."
    )


def test_prompt_is_grounded_in_the_retrieved_agents(results):
    chat = FakeChat()
    generation.summarize("code editor", results, client=chat)

    system, human = chat.calls[0]
    assert system[0] == "system"
    assert "from that tool's own block" in system[1]

    prompt = human[1]
    assert "User need: code editor" in prompt
    assert "[1] Cursor" in prompt
    assert "[2] Aider" in prompt
    assert "Electron,GPT-4" in prompt


def test_only_the_top_results_are_sent(results, monkeypatch):
    monkeypatch.setattr(config, "SUMMARY_MAX_RESULTS", 1)
    chat = FakeChat()
    generation.summarize("code editor", results, client=chat)
    prompt = chat.calls[0][1][1]
    assert "[1] Cursor" in prompt
    assert "Aider" not in prompt


def test_disabled_by_configuration(results, monkeypatch):
    monkeypatch.setattr(config, "ENABLE_SUMMARY", False)
    chat = FakeChat()
    assert generation.summarize("q", results, client=chat) is None
    assert chat.calls == []


def test_no_results_means_no_summary():
    chat = FakeChat()
    assert generation.summarize("q", [], client=chat) is None
    assert chat.calls == []


def test_model_failure_returns_none_instead_of_raising(results):
    """Ollama down, or the chat model not pulled."""
    chat = FakeChat(error=RuntimeError("model 'llama3.2' not found"))
    assert generation.summarize("q", results, client=chat) is None


def test_timeout_returns_none(results):
    chat = FakeChat(error=TimeoutError("read timed out"))
    assert generation.summarize("q", results, client=chat) is None


def test_blank_output_is_treated_as_no_summary(results):
    assert generation.summarize("q", results, client=FakeChat("   \n  ")) is None


def test_non_text_output_is_rejected(results):
    """Some models return content blocks rather than a plain string."""
    assert generation.summarize("q", results, client=FakeChat([{"type": "text"}])) is None


def test_output_is_stripped(results):
    assert generation.summarize("q", results, client=FakeChat("  answer  ")) == "answer"


def test_prompt_survives_sparse_records():
    sparse = [{"metadata": {}}, {"name": "OnlyName", "metadata": {}}]
    prompt = generation.build_prompt("q", sparse)
    assert "[1] Unknown" in prompt
    assert "[2] OnlyName" in prompt


def test_each_agent_gets_its_own_block(results):
    """Attributes must be unambiguously bound to one tool, not run together."""
    prompt = generation.build_prompt("code editor", results)
    cursor_block, aider_block = prompt.split("[2] Aider")
    assert "Electron,GPT-4" in cursor_block
    assert "Electron,GPT-4" not in aider_block
    assert "Python,Git" in aider_block
    assert "Python,Git" not in cursor_block


def test_prompt_states_how_many_tools_were_given(results):
    assert "Candidate tools (2):" in generation.build_prompt("q", results)


def test_prompt_labels_every_field(results):
    prompt = generation.build_prompt("q", results)
    for label in ("Category:", "Tech:", "Description:"):
        assert label in prompt


def test_system_prompt_forbids_cross_attribution():
    assert "another tool's fields" in generation.SYSTEM_PROMPT
    assert "not in the list" in generation.SYSTEM_PROMPT
