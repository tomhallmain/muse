"""Unit tests for Ollama streaming response assembly in extensions.llm."""

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_spec = importlib.util.spec_from_file_location(
    "llm_standalone", _ROOT / "extensions" / "llm.py"
)
_llm = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_llm)

LLM = _llm.LLM
LLMResult = _llm.LLMResult
StreamChunk = _llm.StreamChunk
accumulate_ollama_stream_events = _llm.accumulate_ollama_stream_events

_spec_red = importlib.util.spec_from_file_location(
    "llm_redundancy_standalone", _ROOT / "extensions" / "llm_redundancy.py"
)
_red = importlib.util.module_from_spec(_spec_red)
assert _spec_red.loader is not None
_spec_red.loader.exec_module(_red)

DefaultRedundancyPolicy = _red.DefaultRedundancyPolicy
truncate_duplicate_paragraph = _red.truncate_duplicate_paragraph


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
