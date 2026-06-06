"""Unit tests for Ollama streaming response assembly in extensions.llm."""

import importlib.util
import json
import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Load sibling modules without executing extensions/__init__.py (circular imports).
def _ensure_extensions_namespace() -> None:
    pkg = sys.modules.get("extensions")
    if pkg is not None and getattr(pkg, "__path__", None):
        return
    namespace = types.ModuleType("extensions")
    namespace.__path__ = [str(_ROOT / "extensions")]
    sys.modules["extensions"] = namespace


_ensure_extensions_namespace()

_spec_red = importlib.util.spec_from_file_location(
    "extensions.llm_redundancy", _ROOT / "extensions" / "llm_redundancy.py"
)
_red = importlib.util.module_from_spec(_spec_red)
assert _spec_red.loader is not None
sys.modules["extensions.llm_redundancy"] = _red
_spec_red.loader.exec_module(_red)

_spec = importlib.util.spec_from_file_location(
    "extensions.llm", _ROOT / "extensions" / "llm.py"
)
_llm = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["extensions.llm"] = _llm
_spec.loader.exec_module(_llm)

LLM = _llm.LLM
LLMResult = _llm.LLMResult
StreamChunk = _llm.StreamChunk
accumulate_ollama_stream_events = _llm.accumulate_ollama_stream_events

DefaultRedundancyPolicy = _red.DefaultRedundancyPolicy
truncate_duplicate_paragraph = _red.truncate_duplicate_paragraph
visible_text_for_policy = _red.visible_text_for_policy
strip_thinking_blocks = _red.strip_thinking_blocks
streaming_visible_response = _red.streaming_visible_response
THINKING_OPEN_TAG = _red.THINKING_OPEN_TAG
THINKING_CLOSE_TAG = _red.THINKING_CLOSE_TAG
USE_INSTANCE_REDUNDANCY = _llm._USE_INSTANCE_REDUNDANCY


def _ndjson_lines(*objects) -> list[bytes]:
    return [json.dumps(obj).encode("utf-8") + b"\n" for obj in objects]


class TestAccumulateOllamaStreamEvents:
    def test_accumulates_deltas_and_uses_final_metadata(self):
        lines = _ndjson_lines(
            {"response": "Hello", "done": False},
            {"response": ", world!", "done": False},
            {
                "response": "",
                "done": True,
                "done_reason": "stop",
                "context": [1, 2, 3],
                "eval_count": 42,
                "total_duration": 100,
            },
        )
        accumulated, final = accumulate_ollama_stream_events(lines)
        assert accumulated == "Hello, world!"
        assert final["done"] is True
        assert final["eval_count"] == 42

        result = LLMResult.from_json({**final, "response": accumulated}, context_provided=True)
        assert result.response == "Hello, world!"
        assert result.context == [1, 2, 3]
        assert result.eval_count == 42

    def test_skips_blank_lines(self):
        lines = [b"\n", json.dumps({"response": "ok", "done": True}).encode("utf-8")]
        accumulated, final = accumulate_ollama_stream_events(lines)
        assert accumulated == "ok"
        assert final["done"] is True


class TestStreamChunk:
    def test_fields(self):
        chunk = StreamChunk(text="a", accumulated="xy", done=False)
        assert chunk.text == "a"
        assert chunk.accumulated == "xy"
        assert chunk.done is False


class TestDefaultRedundancyPolicy:
    def test_repeated_paragraph_stops(self):
        policy = DefaultRedundancyPolicy(min_length=10, min_paragraph_length=5)
        para = "The quick brown fox jumps over the lazy dog."
        accumulated = para + "\n\n" + "Intro.\n\n" + para
        chunk = StreamChunk(text=para[-4:], accumulated=accumulated, done=False)
        verdict = policy.on_chunk(chunk)
        assert verdict.should_stop
        assert verdict.reason == "repeated_paragraph"

    def test_truncate_duplicate_paragraph(self):
        text = "First.\n\nSecond.\n\nSecond."
        assert truncate_duplicate_paragraph(text) == "First.\n\nSecond."


class TestLLMStreamingFlags:
    def test_instance_streaming_default_off(self):
        llm = LLM()
        assert llm.use_streaming is False

    def test_build_payload_stream_flag(self):
        llm = LLM(model_name="test-model")
        data, _ = llm._build_generate_payload("hi", stream=True)
        assert data["stream"] is True
        data_off, _ = llm._build_generate_payload("hi", stream=False)
        assert data_off["stream"] is False

    def test_explicit_none_disables_instance_redundancy(self):
        llm = LLM(use_redundancy_elimination=True)
        assert llm._resolve_redundancy_policy(USE_INSTANCE_REDUNDANCY) is not None
        assert llm._resolve_redundancy_policy(None) is None

    def test_json_path_disables_stream_and_redundancy(self, monkeypatch):
        llm = LLM(use_streaming=True, use_redundancy_elimination=True)
        captured = {}

        def fake_async(*args, **kwargs):
            captured.update(kwargs)
            return LLMResult(
                response='{"key": "value"}',
                context=None,
                context_provided=False,
                created_at="",
                done=True,
                done_reason="stop",
                total_duration=0,
                load_duration=0,
                prompt_eval_count=0,
                prompt_eval_duration=0,
                eval_count=0,
                eval_duration=0,
            )

        monkeypatch.setattr(llm, "generate_response_async", fake_async)
        llm.generate_json_get_value("prompt", "key")
        assert captured["stream"] is False
        assert captured["redundancy_policy"] is None


class TestThinkingModelStreaming:
    def test_visible_text_empty_while_thinking_open(self):
        raw = THINKING_OPEN_TAG + "internal monologue"
        assert visible_text_for_policy(raw) == ""

    def test_visible_text_after_thinking_closed(self):
        raw = THINKING_OPEN_TAG + "think" + THINKING_CLOSE_TAG + "\n\nHello world"
        assert visible_text_for_policy(raw) == "Hello world"

    def test_strip_thinking_blocks_removes_stray_tags(self):
        text = "Answer " + THINKING_OPEN_TAG + "oops" + THINKING_CLOSE_TAG + " here"
        assert strip_thinking_blocks(text) == "Answer oops here"

    def test_streaming_visible_response(self):
        raw = THINKING_OPEN_TAG + "x" + THINKING_CLOSE_TAG + "\n\nFinal answer."
        assert streaming_visible_response(raw) == "Final answer."

    def test_strip_thinking_blocks_redacted_thinking_alias(self):
        alias = "redacted_" + "thinking"
        open_tag = "<" + alias + ">"
        close_tag = "</" + alias + ">"
        raw = open_tag + "\ninternal\n" + close_tag + "\n\nHey Leute,"
        assert strip_thinking_blocks(raw) == "Hey Leute,"

    def test_clean_response_for_models_strips_think_tags(self):
        llm = LLM(model_name="llama3")
        raw = THINKING_OPEN_TAG + "planning\n" + THINKING_CLOSE_TAG + "\n\nHello!"
        assert llm._clean_response_for_models(raw) == "Hello!"
