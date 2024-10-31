import datetime
import os
from copy import deepcopy
import urllib.request
from bs4 import BeautifulSoup


def get_elements(class_path=[["class","*"]], parent=None):
    assert parent is not None
    all_elements = []
    type_def = class_path[0]
    _type = type_def[0]
    value = type_def[1]
    
    lowest_class = len(class_path) == 1

    if _type == "class":
        elements = parent.find_all(class_=value)
    elif _type == "id":
        elements = parent.find_all(id=value)
    elif _type == "tag":
        elements = parent.find_all(value)
    else:
        raise Exception("Unhandled type: " + _type)

    # print(f"Found {len(elements)} elements of {_type}={value}")
    
    if lowest_class:
        all_elements = elements
    else:
        for element in elements:
            all_elements.extend(get_elements(class_path[1:], element))

    return all_elements

def get_element_texts(class_path=[["class","*"]], start_element=None):
    out = []
    try:
        for element in get_elements(class_path, start_element):
            out.append(element.text)
    except Exception as e:
        print(f"Failed to find elements of class {class_path} - {e}")
    return out

def extract_int_from_start(s):
    out = ""
    for c in s:
        if c.isdigit():
            out += c
        else:
            break
    return int(out)


class HackerNewsItem:
    def __init__(self, id, titleline_el):
        titleline_links = get_elements(class_path=[["tag", "a"]], parent=titleline_el)
        if len(titleline_links) > 2:
            print("Unexpected number of title line links found: " + str(len(titleline_links)))
        elif len(titleline_links) == 1:
            return # No source == no article
        elif len(titleline_links) == 0:
            print(titleline_el)
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
        age_str = subline_el.find(class_="age").attrs["title"]
        date = datetime.datetime.fromtimestamp(int(age_str.split(" ")[1]))
        comments_el = subline_el.select_one('a[href*="item?id="]')
        self.points = extract_int_from_start(score_el.text)
        self.user = subline_el.find(class_="hnuser").text
        self.age = date
        self.comments = extract_int_from_start(comments_el.text)

    def __str__(self):
        current_date = datetime.datetime.now()
        if self.age > current_date - datetime.timedelta(days=1):
            time_str = "today"
        elif self.age > current_date - datetime.timedelta(days=30):
            time_str = "on " + self.age.strftime("%Y-%m-%d")
        else:
            time_str = "over a month ago"
        comments_str = ""
        if self.comments < 100:
            comments_str = ""
        elif self.comments < 200:
            "(100+ comments - some engagement)"
        else:
            "(200+ comments - this news is generating very high engagement)"
        return f"""{self.title} (from {self.source} {time_str}) {comments_str}"""

class HackerNewsSouper():

    @staticmethod
    def get_hacker_news_soup():
        try:
            url = f"https://news.ycombinator.com"
            response = urllib.request.urlopen(url)
            html_string = response.read().decode("utf-8")
            soup = BeautifulSoup(html_string, "lxml")
            return soup
        except Exception as e:
            raise Exception(f"Failed to get HTML for Hacker News: {e}")

    @staticmethod
    def get_hacker_news_items():
        # There is one table with alternating classes containing title and subline, so need to update the news item on every other row.
        soup = HackerNewsSouper.get_hacker_news_soup()
        items = []
        main_table = get_elements(class_path=[["tag", "table"]], parent=soup)[2]
        row_els = get_elements(class_path=[["tag", "tr"]], parent=main_table)
        if len(row_els) < 10:
            raise Exception(f"Not enough news rows found!")

        hacker_news_item = None

        for el in row_els:
            if el.has_attr("id"):
                id = el.attrs["id"]
                if id != "pagespace":
                    titleline_el = el.find(class_="titleline")
                    if titleline_el is None:
                        print("Failed to get titleline_el for Hacker New items")
                    else:
                        try:
                            hacker_news_item = HackerNewsItem(id, titleline_el)
                        except Exception as e:
                            print(f"Failed to create Hacker News Item: {e}")
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
                        print(el)
                        print("Failed to extract data for Hacker New items: " + str(e))
                hacker_news_item = None

        return items
    
    @staticmethod
    def get_news(total=15):
        news_items = HackerNewsSouper.get_hacker_news_items()
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

