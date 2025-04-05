"""LLM interface for the Muse application."""

import json
from urllib import request
from dataclasses import dataclass
from typing import Optional, List
import random  # Add this at the top with other standard library imports

from utils import Utils


class LLMResponseException(Exception):
    """Raised when LLM call fails"""
    pass


@dataclass
class LLMResult:
    """Encapsulates the response data from an Ollama LLM call."""
    response: str
    context: Optional[List[int]]
    context_provided: bool
    created_at: str
    done: bool
    done_reason: Optional[str]
    total_duration: int
    load_duration: int
    prompt_eval_count: int
    prompt_eval_duration: int
    eval_count: int
    eval_duration: int

    @classmethod
    def from_json(cls, data: dict, context_provided=False) -> 'LLMResult':
        """Create a LLMResult instance from the JSON response data."""
        return cls(
            response=data.get("response", ""),
            context=data.get("context", None),
            context_provided=context_provided,
            created_at=data.get("created_at", ""),
            done=data.get("done", False),
            done_reason=data.get("done_reason", ""),
            total_duration=data.get("total_duration", 0),
            load_duration=data.get("load_duration", 0),
            prompt_eval_count=data.get("prompt_eval_count", 0),
            prompt_eval_duration=data.get("prompt_eval_duration", 0),
            eval_count=data.get("eval_count", 0),
            eval_duration=data.get("eval_duration", 0)
        )

    def _get_json_attr(self, attr_name):
        try:
            if attr_name is None or attr_name.strip() == "":
                raise Exception(f"Invalid attr name: \"{attr_name}\"")
            json_str = self.response
            if json_str is None or json_str.strip() == "" or ("{" not in json_str or "}" not in json_str or ":" not in json_str):
                raise Exception("No or malformed JSON object found in JSON string!")
            json_str = json_str.replace("```", "").strip()
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()
            json_obj = json.loads(json_str)
            assert(isinstance(json_obj, dict))
            if attr_name not in json_obj:
                for key in json_obj.keys():
                    if Utils.is_similar_strings(attr_name, key):
                        self.response = json_obj[key]
                        return self
            self.response = json_obj[attr_name]
            return self
        except Exception as e:
            Utils.log_red(f"{e} - Failed to get json attr {attr_name} from json response: {json}")
            return None


class LLM:
    ENDPOINT = "http://localhost:11434/api/generate"
    DEFAULT_TIMEOUT = 180
    DEFAULT_SYSTEM_PROMPT_DROP_RATE = 0.9  # 90% chance to drop system prompt

    def __init__(self, model_name="deepseek-r1:14b"):
        self.model_name = model_name
        Utils.log(f"Using LLM model: {self.model_name}")

    def ask(self, query, json_key=None, timeout=DEFAULT_TIMEOUT, context=None, system_prompt=None, system_prompt_drop_rate=DEFAULT_SYSTEM_PROMPT_DROP_RATE):
        """Ask the LLM a question and optionally extract a JSON value."""
        if json_key is not None:
            return self.generate_json_get_value(query, json_key, timeout=timeout, context=context, system_prompt=system_prompt, system_prompt_drop_rate=system_prompt_drop_rate)
        return self.generate_response(query, timeout=timeout, context=context, system_prompt=system_prompt, system_prompt_drop_rate=system_prompt_drop_rate)

    def generate_response(self, query, timeout=DEFAULT_TIMEOUT, context=None, system_prompt=None, system_prompt_drop_rate=DEFAULT_SYSTEM_PROMPT_DROP_RATE):
        """Generate a response from the LLM."""
        query = self._sanitize_query(query)
        timeout = self._get_timeout(timeout)
        Utils.log(f"Asking LLM {self.model_name}:\n{query}")
        data = {
            "model": self.model_name,
            "prompt": query,
            "stream": False,
            # "options": { # TODO enable more options for LLM queries
            #     "temperature": 0.7,
            #     "top_p": 0.9,
            #     "num_predict": 1024,
            #     "stop": ["</s>", "EOL"],
            #     "num_ctx": 4096,
            #     "timeout": timeout * 1000  # Convert to milliseconds
            # }
        }
        
        if context is not None:
            data["context"] = context
            
        # Randomly decide whether to include system prompt
        if system_prompt is not None and random.random() > system_prompt_drop_rate:
            data["system"] = system_prompt
            Utils.log_debug("Including system prompt in LLM request")
        elif system_prompt is not None:
            Utils.log_debug("Dropping system prompt from LLM request")
            
        req = request.Request(
            LLM.ENDPOINT,
            headers={"Content-Type": "application/json"},
            data=json.dumps(data).encode("utf-8"),
        )
        try:
            response = request.urlopen(req, timeout=timeout).read().decode("utf-8")
            resp_json = json.loads(response)
            result = LLMResult.from_json(resp_json, context_provided=context is not None)
            result.response = self._clean_response_for_models(result.response)
            return result
        except Exception as e:
            Utils.log_red(f"Failed to generate LLM response: {e}")
            raise LLMResponseException(f"Failed to generate LLM response: {e}")

    def generate_json_get_value(self, query, json_key, timeout=DEFAULT_TIMEOUT, context=None, system_prompt=None, system_prompt_drop_rate=DEFAULT_SYSTEM_PROMPT_DROP_RATE):
        """Generate a response and extract a specific JSON value."""
        result = self.generate_response(query, timeout=timeout, context=context, system_prompt=system_prompt, system_prompt_drop_rate=system_prompt_drop_rate)
        return result._get_json_attr(json_key)

    def _is_thinking_model(self) -> bool:
        """Check if the current model is a thinking model that uses internal prompts."""
        return self.model_name.startswith("deepseek-r1")

    def _clean_response_for_models(self, response_text):
        if self._is_thinking_model():
            if response_text.strip().startswith("<think>") and "</think>" in response_text:
                response_text = response_text[response_text.index("</think>") + len("</think>"):].strip()
        return response_text

    def _sanitize_query(self, query):
        return query

    def _get_timeout(self, timeout=DEFAULT_TIMEOUT):
        if self._is_thinking_model():
            # Thinking models have internal prompt mechanisms which
            # can take a while to complete for complex requests.
            return max(timeout, 300)
        return timeout


if __name__ == "__main__":
    llm = LLM()
    print(llm.generate_response("What is the meaning of life?"))
