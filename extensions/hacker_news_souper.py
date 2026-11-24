import datetime

from extensions.soup_utils import SoupUtils
from library_data.blacklist import Blacklist
from utils.logging_setup import get_logger
from utils.translations import I18N

_ = I18N._

logger = get_logger(__name__)

class HackerNewsItem:
    def __init__(self, id, titleline_el):
        titleline_links = SoupUtils.get_elements(class_path=[["tag", "a"]], parent=titleline_el)
        if len(titleline_links) > 2:
            logger.warning(_("Unexpected number of title line links found: {0}").format(len(titleline_links)))
        elif len(titleline_links) == 1:
            return # No source == no item
        elif len(titleline_links) == 0:
            logger.warning(titleline_el)
            raise Exception("No title line links found: " + str(len(titleline_links)))
        self.id = id
        self.title = titleline_links[0].text
        self.url = titleline_links[0].attrs["href"]
        self.source = titleline_links[1].text if len(titleline_links) > 1 else ""
        self.points = -1
        self.user = None
        self.age = datetime.datetime.strptime("1/1/1970", "%d/%m/%Y")
        self.comments = -1

    def update_for_subline(self, subline_el):
        score_el = subline_el.find(class_="score")
        self.points = SoupUtils.extract_int_from_start(score_el.text) if score_el is not None else -1
        user_el = subline_el.find(class_="hnuser") or subline_el.select_one('a[href^="user?id="]')
        self.user = user_el.text if user_el is not None else None
        self.age = HackerNewsItem._parse_age(subline_el.find(class_="age").attrs["title"])
        # The age link also points to item?id=, so the comments link is the last one.
        item_links = subline_el.select('a[href*="item?id="]')
        comments_text = item_links[-1].text if item_links else ""
        self.comments = SoupUtils.extract_int_from_start(comments_text) if comments_text[:1].isdigit() else 0

    @staticmethod
    def _parse_age(age_title):
        """Local naive datetime from the age title: "<ISO UTC time>", optionally followed by a Unix timestamp."""
        parts = age_title.split()
        if len(parts) > 1 and parts[1].isdigit():
            return datetime.datetime.fromtimestamp(int(parts[1]))
        utc_time = datetime.datetime.fromisoformat(parts[0]).replace(tzinfo=datetime.timezone.utc)
        return utc_time.astimezone().replace(tzinfo=None)

    def __str__(self):
        current_date = datetime.datetime.now()
        if self.age > current_date - datetime.timedelta(days=1):
            time_str = "today"
        elif self.age > current_date - datetime.timedelta(days=30):
            time_str = "on " + self.age.strftime("%Y-%m-%d")
        else:
            time_str = "over a month ago"
        if self.comments < 100:
            comments_str = ""
        elif self.comments < 200:
            comments_str = "(100+ comments - some engagement)"
        else:
            comments_str = "(200+ comments - this news is generating very high engagement)"
        return f"""{self.title} (from {self.source} {time_str}) {comments_str}"""

class HackerNewsSouper():

    @staticmethod
    def get_hacker_news_items():
        # There is one table with alternating classes containing title and subline, so need to update the news item on every other row.
        soup = SoupUtils.get_soup("https://news.ycombinator.com")
        items = []
        main_table = SoupUtils.get_elements(class_path=[["tag", "table"]], parent=soup)[2]
        row_els = SoupUtils.get_elements(class_path=[["tag", "tr"]], parent=main_table)
        if len(row_els) < 10:
            raise Exception(f"Not enough news rows found!")

        hacker_news_item = None

        for el in row_els:
            if el.has_attr("id"):
                id = el.attrs["id"]
                if id != "pagespace":
                    titleline_el = el.find(class_="titleline")
                    if titleline_el is None:
                        logger.warning(_("Failed to get titleline_el for Hacker New items"))
                    else:
                        try:
                            hacker_news_item = HackerNewsItem(id, titleline_el)
                        except Exception as e:
                            logger.warning(_("Failed to create Hacker News Item: {0}").format(e))
            else:
                subline_el = el.find(class_="subline")
                if subline_el is not None:
                    if hacker_news_item is None:
                        raise Exception("Hacker News Item not created yet!")
                    try:
                        hacker_news_item.update_for_subline(subline_el)
                        if hasattr(hacker_news_item, "id") and hacker_news_item.id is not None:
                            items.append(hacker_news_item)
                    except Exception as e:
                        logger.error(el)
                        logger.error(_("Failed to extract data for Hacker New items: {0}").format(e))
                hacker_news_item = None

        return items

    @staticmethod
    def get_nonblacklisted_stories(items=[]):
        headlines = []
        for item in items:
            blacklist_items = list(Blacklist.find_blacklisted_items(item.title).keys())
            if len(blacklist_items) > 0:
                logger.info(f"item blacklisted: {item.title} ({blacklist_items})")
            else:
                headlines.append(item)
        return headlines

    @staticmethod
    def get_news(total=15):
        news_items = HackerNewsSouper.get_hacker_news_items()
        news_items = HackerNewsSouper.get_nonblacklisted_stories(news_items)
        if len(news_items) < 2:
            raise Exception("Not enough valid news found! Check log for blacklist reasons.")
        out = "Today's top stories from Hacker News:\n"
        counter = 0
        for item in news_items:
            if total > -1 and counter >= total:
                break
            counter += 1
            out += f"{item}\n"
        return out


if __name__ == "__main__":
    HackerNewsSouper.get_hacker_news_items()

