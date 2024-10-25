
import json
from urllib import request

class LLM:
    ENDPOINT = "http://localhost:11434/api/generate"

    def __init__(self, model_name="llama2-uncensored:latest"):
        self.model_name = model_name

    def generate_response(self, query):
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
        response = request.urlopen(req).read().decode("utf-8")
        resp_json = json.loads(response)
        return resp_json["response"]


if __name__ == "__main__":
    llm = LLM()
    print(llm.generate_response("What is the meaning of life?"))
