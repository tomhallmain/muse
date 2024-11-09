
import requests


class WikiOpenSearchResponse:
    def __init__(self, json: dict) -> None:
        self._json = json
        self.query = json[0]
        self.articles = []
        if len(self._json[1])!= len(self._json[3]):
            raise ValueError('Invalid JSON format, different number of titles and URLs found')
        for i in range(len(self._json[1])):
            self.articles.append((self._json[1][i], self._json[3][i]))


class WikiOpenSearchAPI:
    BASE_URL = 'https://en.wikipedia.org/w/api.php'

    def __init__(self) -> None:
        pass

    def __build_url(self, query: str):
        return f'{self.BASE_URL}?action=opensearch&search={query}&format=json'

    def search(self, query: str):
        try:
            req = requests.get(self.__build_url(query))
            return WikiOpenSearchResponse(req.json())
        except Exception as e:
            print(f"Failed to connect to Wiki OpenSearch API: {e}")
            return None
