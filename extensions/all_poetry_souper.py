from extensions.soup_utils import SoupUtils


class AllPoetryPoem:
    def __init__(self, id, titleline_el):
        titleline_links = SoupUtils.get_elements(class_path=[["tag", "a"]], parent=titleline_el)
        # if len(titleline_links) > 2:
        #     Utils.log_yellow("Unexpected number of title line links found: " + str(len(titleline_links)))
        # elif len(titleline_links) == 1:
        #     return # No source == no article
        # elif len(titleline_links) == 0:
        #     Utils.log_yellow(titleline_el)
        #     raise Exception("No title line links found: " + str(len(titleline_links)))
        # self.id = id
        # self.url = titleline_links[0].attrs["href"]
        # self.source = titleline_links[1].text if len(titleline_links) > 1 else ""
        # self.age = datetime.datetime.strptime("1/1/1970", "%d/%m/%Y")
        # self.comments = -1
        self.title = None

    def __str__(self):
        return self.title

class AllPoetrySouper():
    BASE_URL = "https://www.allpoetry.org/" # TODO

    @staticmethod
    def get_poems():
        soup = SoupUtils.get_soup(AllPoetrySouper.BASE_URL)
        items = []
        return items
    

if __name__ == "__main__":
    AllPoetrySouper.get_poems()

