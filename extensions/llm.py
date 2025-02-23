
import json
from urllib import request

from utils.utils import Utils

class LLMResponseException(Exception):
    """Raised when LLM call fails"""
    pass

class LLM:
    ENDPOINT = "http://localhost:11434/api/generate"

    def __init__(self, model_name="deepseek-r1:14b"):
        self.model_name = model_name
        Utils.log(f"Using LLM model: {self.model_name}")

    def generate_response(self, query, timeout=120):
        """
        Generates a response using the LLM model.
        """
        query = self._sanitize_query(query)
        timeout = self._get_timeout(timeout)
        Utils.log(f"Asking LLM {self.model_name}:\n{query}")
        data = {
            "model": self.model_name,
            "prompt": query,
            "stream": False,
        }
        data = json.dumps(data).encode("utf-8")
        req = request.Request(
            LLM.ENDPOINT,
            headers={"Content-Type": "application/json"},
            data=data,
        )
        try:
            response = request.urlopen(req, timeout=timeout).read().decode("utf-8")
            resp_json = json.loads(response)
            response_text = resp_json["response"]
            return self._clean_response_for_models(response_text)
        except Exception as e:
            Utils.log_red(f"Failed to generate LLM response: {e}")
            raise LLMResponseException(f"Failed to generate LLM response: {e}")

    def _clean_response_for_models(self, response_text):
        if self.model_name.startswith("deepseek"):
            if response_text.strip().startswith("<think>") and "</think>" in response_text:
                response_text = response_text[response_text.index("</think>") + len("</think>"):].strip()
        return response_text

    def _sanitize_query(self, query):
        return query

    def _get_timeout(self, timeout):
        if self.model_name.startswith("deepseek"):
            # Deepseek models have a <think> internal prompt mechanism which
            # can take a while to complete for complex requests.
            return max(timeout, 200)
        return timeout


if __name__ == "__main__":
    llm = LLM()
    print(llm.generate_response("What is the meaning of life?"))
