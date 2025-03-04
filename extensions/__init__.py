"""Extensions package for the Muse application."""

from extensions.all_poetry_souper import AllPoetrySouper
from extensions.calendar_aggregator import CalendarAggregator
from extensions.hacker_news_souper import HackerNewsSouper
from extensions.imslp_souper import ImslpSouper
from extensions.library_extender import LibraryExtender
from extensions.llm import LLM
from extensions.news_api import NewsAPI
from extensions.open_weather import OpenWeatherAPI
from extensions.soup_utils import SoupUtils
from extensions.wiki_opensearch_api import WikiOpenSearchAPI
from extensions.wiki_souper import WikiSouper

__all__ = [
    'AllPoetrySouper',
    'CalendarAggregator',
    'HackerNewsSouper',
    'ImslpSouper',
    'LibraryExtender',
    'LLM',
    'NewsAPI',
    'OpenWeatherAPI',
    'SoupUtils',
    'WikiOpenSearchAPI',
    'WikiSouper',
] 