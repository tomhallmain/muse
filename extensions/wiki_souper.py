import datetime
import pandas as pd

from extensions.soup_utils import SoupUtils


class WikiTable():
    def __init__(self, table):
        self.df = SoupUtils.get_table_data(table)

    def __str__(self):
        return str(self.df)

class WikiSection():
    def __init__(self, header, tables=[]):
        self._header = header.text
        if self._header and self._header.endswith("[edit]"):
            self._header = self._header[:-6]
        self._tables = []
        for table in tables:
            self._tables.append(WikiTable(table))

    def add_table(self, table):
        self._tables.append(WikiTable(table))
    
    def __str__(self):
        out = self._header + '\n'
        for table in self._tables:
            out += str(table) + '\n'
        return out


class WikiSouper():

    @staticmethod
    def get_wiki_main_content(soup):
        main = soup.find('main', {'id:': 'content'})
        return main

    @staticmethod
    def get_wiki_body_content(soup):
        body = soup.find('div', {'id': 'bodyContent'})
        return body

    @staticmethod
    def get_mw_content(soup):
        mw = soup.find('div', {'class': 'mw-content-ltr'})
        return mw

    @staticmethod
    def get_wiki_tables(wiki_url):
        # There is one table with alternating classes containing title and subline, so need to update the news item on every other row.
        soup = SoupUtils.get_soup(wiki_url)
        items = []
        body_content = WikiSouper.get_mw_content(soup)
        tables = SoupUtils.get_elements(class_path=[["tag", "table"]], parent=body_content)
        sections = []
        section = None

        for el in body_content.contents:
            if el.name == 'div' and el.has_attr('class') and len(el['class']) > 0 and el['class'][0] == 'mw-heading':
                if section is not None:
                    sections.append(section)
                section = WikiSection(el)
            if el.name == 'table':
                section.add_table(el)

        for section in sections:
            print(section)

        return items
    

if __name__ == "__main__":
    WikiSouper.get_wiki_tables("https://en.wikipedia.org/wiki/List_of_compositions_by_George_Frideric_Handel")
