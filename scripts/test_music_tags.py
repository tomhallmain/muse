import os

# Change to the root directory
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

import music_tag


test_file = r"F:\iTunes Music\conductor Evgeny Svetlanov\Symphony No. 3\03 5th Movement_ Lustig En Tempo Und.m4a"

f = music_tag.load_file(test_file)

for k, v in f.__dict__["tag_map"].items():
    try:
        val = f[k]
        print(f"{k} : {val} (class = {type(val.first)})")
    except KeyError as e:
        pass
