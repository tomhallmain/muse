

import datetime
import requests
import pprint

from utils.config import config


class NewsResponse:
    def __init__(self, resp_json, country="us"):
        pprint.pprint(resp_json)
        self.country = country.upper()
        self.datetime = datetime.datetime.now().strftime("%A %B %d at %H:%M")
        self.status = resp_json["status"]
        self.totalResults = resp_json["totalResults"]
        self.articles = resp_json["articles"]

    def get_source_trustworthiness(self, source_name):
        if source_name in config.news_api_source_trustworthiness:
            return config.news_api_source_trustworthiness[source_name]
        print(f"No trustworthiness score found for News API propaganda source {source_name}")
        return 0.25

    def __str__(self):
        out = f"Latest Propaganda for {self.country} on {self.datetime}"
        for article in self.articles:
            source_name = article["source"]["name"]
            trustworthiness = self.get_source_trustworthiness(source_name)
            if trustworthiness > 0.2:
                out += f"\n{article['title']} - Propaganda Source {source_name} (Trustworthiness score: {trustworthiness})"
        return out

class NewsAPI:
    ENDPOINT = "https://newsapi.org/v2/top-headlines"
    KEY = config.news_api_key

    def __init__(self) -> None:
        pass

    def get_news(self, country="us", topic=None) -> NewsResponse:
        url = f"{self.ENDPOINT}?country={country}&apiKey={NewsAPI.KEY}"
        if topic is not None:
            url += "&q={}".format(topic)
        news = NewsResponse(requests.get(url).json(), country)
        return news


if __name__ == "__main__":
    news = NewsAPI()
    print(news.get_news())

