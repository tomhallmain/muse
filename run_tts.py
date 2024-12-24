import sys

from tts.tts_runner import Chunker, TextToSpeechRunner

text = """Lang schwang der Klang am Hang entlang"""

preferred_speakers = [
    "Royston Min",
    "Aaron Dreschner",
    "Sofia Hellen",
]

speaker = "Aaron Dreschner"
de_model = ("tts_models/de/thorsten/tacotron2-DDC", None, None)
multi_model = ("tts_models/multilingual/multi-dataset/xtts_v2", speaker, "en")

def cut_str_from_right_by_word(s, max_len=40):
    while len(s) > max_len:
        if not " " in s:
            return s[:max_len]
        s = s[:s.rfind(" ")]
    return s

def main():
    # text_file = "test"
    text_file = sys.argv[1]
    overwrite = (sys.argv[2] == "t" or sys.argv[2] == "T") if len(sys.argv) > 2 else False
    runner = TextToSpeechRunner(multi_model, filepath=text_file, overwrite=overwrite)

    runner.speak_file(text_file)

    # while True:
    #     try:
    #         text = input("Text: ")
    #         if text.strip() != "":
    #             try:
    #                 runner.speak(text)
    #             except Exception as e:
    #                 Utils.log_red("Failed to speak text: " + text)
    #                 Utils.log_red(e)
    #     except KeyboardInterrupt:
    #         break

    # failures = []
    # for line in Chunker.get_chunks(text_file, split_on_each_line=True):
    #     if line.strip() != "":
    #         try:
    #             runner.set_output_path(cut_str_from_right_by_word(line))
    #             runner.speak(line)
    #         except Exception as e:
    #             Utils.log_red("Failed to speak text: " + line)
    #             failures.append((line, e))

    # if len(failures) > 0:
    #     Utils.log("|--------------------------------------------------|")
    #     Utils.log_red("Total failed to speak texts: " + str(len(failures)))
    #     for line, e in failures:
    #         Utils.log(line + ":" + str(e))

if __name__ == '__main__':
    main()
    # for s in Chunker.get_str_chunks(text):
    #     Utils.log(s)
