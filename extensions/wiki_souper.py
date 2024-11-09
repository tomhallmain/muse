import io
import json
import os
import pandas as pd
import time

from extensions.soup_utils import SoupUtils


def clean_wiki_text(text):
    if text is None or type(text) != str:
        return text
    text = text.strip()
    if text.endswith(']') and "[" in text:
        text = text[:text.index("[")]
    return SoupUtils.clean_html(text)


class WikiTable():
    def __init__(self, table=None):
        if table is None:
            self.df = pd.DataFrame()
        elif type(table) == pd.DataFrame:
            self.df = table
        else:
            self.df = SoupUtils.get_table_data(table)
        self.clean_df()

    def clean_df(self):
        for col in self.df:
            self.df[col] = self.df[col].apply(lambda x: clean_wiki_text(x))

    def has_data(self):
        return len(self.df) != 0

    @staticmethod
    def from_json(json):
        return pd.read_json(io.StringIO(json))

    def __str__(self):
        return str(self.df)


class WikiSection():
    def __init__(self, header, tables=[]):
        self._header = header if type(header) == str else header.text
        if self._header and self._header.strip().endswith("]") and "[" in self._header:
            self._header = self._header[:self._header.index("[")]
        if self._header:
            self._header = clean_wiki_text(self._header)
        self._table_temp = None
        self._tables = []
        for table in tables:
            self._tables.append(WikiTable(table))

    def add_table(self, table):
        self._tables.append(WikiTable(table))

    def add_table_part(self, p):
        if self._table_temp is None:
            self._table_temp = pd.DataFrame()
        self._table_temp = self._table_temp._append(pd.DataFrame([p.text.strip()]))

    def combine_temp_table(self):
        if self._table_temp is not None and len(self._table_temp) > 0:
            self._table_temp.reset_index(drop=True, inplace=True)
            self._tables.append(WikiTable(self._table_temp))
            self._table_temp = None

    def has_data(self):
        for table in self._tables:
            if table.has_data():
                return True
        return False

    def json(self):
        return {
            "header": self._header,
            "tables": [
                table.df.to_json() for table in self._tables
            ]
        }

    @staticmethod
    def from_json(data):
        return WikiSection(data["header"], [WikiTable.from_json(t) for t in data["tables"]])

    def __str__(self):
        out = self._header + '\n'
        for table in self._tables:
            out += str(table) + '\n'
        return out


class WikiCompilationData:
    SAVE_LOCATION = os.path.join(os.path.dirname(os.path.dirname(__file__)), "library_data")

    def __init__(self, url, has_tables):
        self._url = url
        self._name = clean_wiki_text(url.replace("https://en.wikipedia.org/wiki/", "").replace("_", " "))
        self._sections = []
        self._has_tables = has_tables

    def add_section(self, section_el):
        section = WikiSection(section_el)
        self._sections.append(section)
        return section

    def has_data(self):
        for section in self._sections:
            if section.has_data():
                return True
        return False

    def json(self):
        return {
            'url': self._url,
            'name': self._name,
            'sections': [section.json() for section in self._sections]
            }

    def save_to_file(self):
        filename = os.path.join(WikiCompilationData.SAVE_LOCATION, self._name + ".json")
        with open(filename, 'w', encoding="utf-8") as f:
            f.write(json.dumps(self.json(), indent=4))

    @staticmethod
    def load_from_file(name):
        with open(name, 'r', encoding="utf-8") as f:
            data = json.loads(f.read())
            wiki_compilation_data = WikiCompilationData(data['url'], None)
            for section in data['sections']:
                wiki_compilation_data._sections.append(WikiSection.from_json(section))
        return wiki_compilation_data


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
    def get_more_citations_needed(soup):
        more = soup.find('table', {'class':'box-More_citations_needed'})
        return more

    @staticmethod
    def get_catlinks(soup):
        catlinks = soup.find('div', {'id': 'catlinks'})
        return catlinks

    @staticmethod
    def get_wiki_tables(wiki_url):
        # There is one table with alternating classes containing title and subline, so need to update the news item on every other row.
        soup = SoupUtils.get_soup(wiki_url)
        body_content = WikiSouper.get_mw_content(soup)
        tables = SoupUtils.get_elements(class_path=[["tag", "table"]], parent=body_content)
        more_citations = WikiSouper.get_more_citations_needed(soup)
        # catlinks = WikiSouper.get_catlinks(soup)
        has_tables = len(tables) > 0 if more_citations is None else len(tables) > 1
        wiki_compilation_data = WikiCompilationData(wiki_url, has_tables)
        section = WikiSection(wiki_compilation_data._name)

        for el in body_content.contents:
            if el.name == 'div' and el.has_attr('class') and len(el['class']) > 0 and el['class'][0] == 'mw-heading':
                if section is not None:
                    if section.has_data() or section._header != wiki_compilation_data._name:
                        section.combine_temp_table()
                        wiki_compilation_data._sections.append(section)
                header = el.contents[0]
                if header.attrs['id'] == 'References':
                    break
                section = wiki_compilation_data.add_section(el)
            if section is not None:
                if el.name == 'table' and wiki_compilation_data._has_tables:
                    section.add_table(el)
                if el.name == 'p' and not wiki_compilation_data._has_tables:
                    section.add_table_part(el)
                if el.name == 'ul' or el.name == 'ol':
                    for li in el.contents:
                        if li.name == 'li':
                            section.add_table_part(li)
                    section.combine_temp_table()
                if el.name == 'dl':
                    for dd in el.contents[0]:
                        if dd.name == 'dd':
                            sub_dl = dd.find('dl')
                            if sub_dl is not None and len(sub_dl.contents[0]) > 1:
                                for dd1 in sub_dl.contents:
                                    if dd1.name == 'dd':
                                        section.add_table_part(dd1)
                            else:
                                section.add_table_part(dd)
                        section.combine_temp_table()

        for section in wiki_compilation_data._sections:
            print(section)

        return wiki_compilation_data

    @staticmethod
    def save_to_files(wiki_urls=[]):
        invalid_data_urls = []
        failed_urls = {}
        for wiki_url in wiki_urls:
            try:
                wiki_compilation_data = WikiSouper.get_wiki_tables(wiki_url)
                wiki_compilation_data.save_to_file()
                if not wiki_compilation_data.has_data():
                    invalid_data_urls.append(wiki_url)
            except Exception as e:
                print("Error gathering data from Wiki url: " + wiki_url)
                print(e)
                failed_urls[wiki_url] = str(e)
                raise e
            print("\n-----------------------------------------------------------\n")
            time.sleep(2)
        
        if len(invalid_data_urls) > 0:
            print("Invalid data urls:")
            for url in invalid_data_urls:
                print(url)

            print("\n-----------------------------------------------------------\n")

        if len(failed_urls) > 0:
            print("Failed urls: ")
            for url, e in failed_urls:
                print(f"{url} - {e}")


if __name__ == "__main__":
    WikiSouper.get_wiki_tables("https://en.wikipedia.org/wiki/List_of_compositions_by_George_Frideric_Handel")


