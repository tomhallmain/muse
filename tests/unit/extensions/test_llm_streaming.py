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
thinking_chars_in_progress = _red.thinking_chars_in_progress
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

    def test_streaming_visible_response_passthrough_for_plain_text(self):
        """streaming_visible_response must be a no-op when no thinking tags are present."""
        plain = "No thinking here, just a normal response."
        assert streaming_visible_response(plain) == plain

    def test_is_thinking_model_covers_known_prefixes(self):
        for model in ("deepseek-r1:14b", "qwen3:8b", "qwq:32b"):
            assert LLM(model_name=model)._is_thinking_model(), f"{model} should be detected"
        for model in ("llama3", "mistral", "phi3"):
            assert not LLM(model_name=model)._is_thinking_model(), f"{model} should not be detected"


class TestCancelOnSkip:
    """Regression tests for cancellation via run_context.should_skip()."""

    def test_skip_during_generation_returns_none_without_error(self, monkeypatch):
        """generate_response_async must return None (not raise) when should_skip
        fires while the generation thread is blocked mid-request.

        Regression: cancel_generation() set self._thread = None, but the old
        code then tried self._thread.join() on the now-None reference, raising
        AttributeError: 'NoneType' object has no attribute 'join'."""
        import threading

        class _SkipAlways:
            def should_skip(self):
                return True

        llm = LLM(model_name="llama3", run_context=_SkipAlways())

        # Block the HTTP call so the thread is still alive when the monitoring
        # loop first calls should_skip() and triggers cancel_generation().
        unblock = threading.Event()

        class _BlockingResp:
            def read(self):
                unblock.wait(timeout=10)
                return json.dumps({"response": "Hello", "done": True}).encode("utf-8")

        monkeypatch.setattr(
            _llm.request, "urlopen", lambda req, timeout=None: _BlockingResp()
        )

        result = llm.generate_response_async("test prompt", stream=False, redundancy_policy=None)
        unblock.set()  # let the background daemon thread exit cleanly
        assert result is None


class TestGenerateResponseBuffered:
    """Tests for the non-streaming (_generate_response_buffered) path."""

    @staticmethod
    def _make_urlopen(response_dict):
        """Return a urlopen stub that reads back *response_dict* as JSON bytes."""
        body = json.dumps(response_dict).encode("utf-8")

        class _FakeResp:
            def read(self):
                return body

        def fake_urlopen(req, timeout=None):
            return _FakeResp()

        return fake_urlopen

    def test_returns_correct_llmresult(self, monkeypatch):
        llm = LLM(model_name="llama3")
        monkeypatch.setattr(
            _llm.request, "urlopen",
            self._make_urlopen({
                "response": "Hello world",
                "done": True,
                "done_reason": "stop",
                "eval_count": 42,
                "total_duration": 1000,
                "load_duration": 100,
                "prompt_eval_count": 5,
                "prompt_eval_duration": 50,
                "eval_duration": 900,
            }),
        )
        result = llm.generate_response("test", stream=False, redundancy_policy=None)
        assert result.response == "Hello world"
        assert result.done is True
        assert result.eval_count == 42
        assert result.truncated is False
        assert result.truncation_reason == ""

    def test_never_sets_truncated(self, monkeypatch):
        """Buffered path must not set truncated=True even when use_redundancy_elimination is on."""
        llm = LLM(model_name="llama3", use_redundancy_elimination=True)
        monkeypatch.setattr(
            _llm.request, "urlopen",
            self._make_urlopen({"response": "Some response text.", "done": True}),
        )
        result = llm.generate_response("test", stream=False, redundancy_policy=None)
        assert result.truncated is False

    def test_strips_thinking_blocks(self, monkeypatch):
        """_clean_response_for_models must strip thinking tags in buffered mode."""
        llm = LLM(model_name="llama3")
        raw = THINKING_OPEN_TAG + "internal plan\n" + THINKING_CLOSE_TAG + "\n\nFinal answer."
        monkeypatch.setattr(
            _llm.request, "urlopen",
            self._make_urlopen({"response": raw, "done": True}),
        )
        result = llm.generate_response("test", stream=False, redundancy_policy=None)
        assert result.response == "Final answer."

    def test_resets_failure_count_on_success(self, monkeypatch):
        """A valid buffered response resets the per-state failure counter."""
        llm = LLM(model_name="llama3")
        llm.increment_failure_count()
        assert llm.get_failure_count() == 1
        monkeypatch.setattr(
            _llm.request, "urlopen",
            self._make_urlopen({"response": "Good response.", "done": True}),
        )
        llm.generate_response("test", stream=False, redundancy_policy=None)
        assert llm.get_failure_count() == 0


class TestThinkingBudget:
    """Tests for the thinking_budget_chars feature in DefaultRedundancyPolicy."""

    def test_thinking_chars_in_progress_open_block(self):
        """Reports chars accumulated inside an unclosed thinking block."""
        content = "some internal reasoning"
        raw = THINKING_OPEN_TAG + content
        assert thinking_chars_in_progress(raw) == len(content)

    def test_thinking_chars_in_progress_closed_block(self):
        """Returns 0 when the thinking block is already closed."""
        raw = THINKING_OPEN_TAG + "reasoning" + THINKING_CLOSE_TAG + "\n\nAnswer."
        assert thinking_chars_in_progress(raw) == 0

    def test_thinking_chars_in_progress_no_tags(self):
        """Returns 0 for plain text with no thinking tags."""
        assert thinking_chars_in_progress("just a normal response") == 0

    def test_budget_not_exceeded_returns_false(self):
        """Policy does not fire when thinking chars are within budget."""
        policy = DefaultRedundancyPolicy(thinking_budget_chars=500)
        raw = THINKING_OPEN_TAG + "x" * 100  # 100 chars, well under 500
        chunk = StreamChunk(text="x", accumulated=raw, done=False)
        assert not policy.on_chunk(chunk).should_stop

    def test_budget_exceeded_fires_verdict(self):
        """Policy fires with reason thinking_budget_exceeded when over budget."""
        policy = DefaultRedundancyPolicy(thinking_budget_chars=50)
        raw = THINKING_OPEN_TAG + "x" * 100  # 100 chars, over budget of 50
        chunk = StreamChunk(text="x", accumulated=raw, done=False)
        verdict = policy.on_chunk(chunk)
        assert verdict.should_stop
        assert verdict.reason == "thinking_budget_exceeded"

    def test_budget_truncate_to_is_empty_string(self):
        """truncate_to is empty so the caller treats this as a failed response."""
        policy = DefaultRedundancyPolicy(thinking_budget_chars=10)
        raw = THINKING_OPEN_TAG + "x" * 50
        chunk = StreamChunk(text="x", accumulated=raw, done=False)
        verdict = policy.on_chunk(chunk)
        assert verdict.truncate_to == ""

    def test_budget_default_is_8000(self):
        """thinking_budget_chars defaults to 8000; fires on absurdly long blocks."""
        policy = DefaultRedundancyPolicy()
        assert policy.thinking_budget_chars == 8_000
        chunk_under = StreamChunk(text="x", accumulated=THINKING_OPEN_TAG + "x" * 100, done=False)
        assert not policy.on_chunk(chunk_under).should_stop
        chunk_over = StreamChunk(text="x", accumulated=THINKING_OPEN_TAG + "x" * 10_000, done=False)
        assert policy.on_chunk(chunk_over).should_stop

    def test_budget_fires_before_redundancy_checks(self):
        """Budget check runs even when visible text is empty (block still open)."""
        # If the redundancy checks ran first they would short-circuit on empty
        # visible text and return False — budget must check before that guard.
        policy = DefaultRedundancyPolicy(
            thinking_budget_chars=10,
            min_length=200,  # would prevent redundancy from firing
        )
        raw = THINKING_OPEN_TAG + "x" * 100
        chunk = StreamChunk(text="x", accumulated=raw, done=False)
        verdict = policy.on_chunk(chunk)
        assert verdict.should_stop
        assert verdict.reason == "thinking_budget_exceeded"
