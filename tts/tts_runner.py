import os
import re
import subprocess
import sys
import time

import torch

from utils.config import config
from utils.job_queue import JobQueue
from utils.utils import Utils

try:
    sys.path.insert(0, config.coqui_tts_location)
    from TTS.api import TTS
    # Utils.remove_extra_handlers()
except ImportError:
    raise Exception("Failed to import Coqui TTS. Ensure the code is downloaded and the \"coqui_tts_location\" value is set in the config.")

import vlc

# from ops.speakers import speakers
from tts.text_cleaner_ruleset import TextCleanerRuleset
from utils.config import config
from utils.job_queue import JobQueue
from utils.utils import Utils

# Get device
device = "cuda" if torch.cuda.is_available() else "cpu"

# List available 🐸TTS models
# pprint.pprint(TTS().list_models())


class Chunker:
    MAX_CHUNK_TOKENS = config.max_chunk_tokens
    cleaner = TextCleanerRuleset()

    @staticmethod
    def _clean(text):
        cleaned = Chunker.cleaner.clean(text)
        if Chunker.count_tokens(cleaned) > 200 and cleaned.startswith("\"") and cleaned.endswith("\""):
            # The sentence segmentation algorithm does not break on quotes even if they are long.
            return cleaned[1:-1]
        return cleaned

    @staticmethod
    def contains_alphanumeric(text):
        return bool(re.search(r'\w', text))

    @staticmethod
    def _yield_chunks(lines_iterable, is_str=False, split_on_each_line=False):
        last_chunk = ""
        chunk = ""
        for line in lines_iterable:
            if split_on_each_line:
                if Chunker.contains_alphanumeric(line):
                    yield Chunker._clean(line.strip())
                continue
            if line.strip() == "":
                if chunk.strip() != "":
                    if Chunker.contains_alphanumeric(chunk):
                        yield Chunker._clean(chunk.strip())
                last_chunk = chunk
                chunk = ""
                continue
            if line.startswith("[") or line.startswith("("):
                continue
            if is_str and len(chunk) > 0 and chunk[-1] != " ":
                chunk += " "
            chunk += line
        if chunk != last_chunk and chunk.strip() != "":
            if Chunker.contains_alphanumeric(chunk):
                yield Chunker._clean(chunk.strip())

    @staticmethod
    def count_tokens(chunk):
        return len(chunk.strip().split(" "))

    @staticmethod
    def split_tokens(chunk, size):
        chunk_tokens = chunk.strip().split(" ")
        return [" ".join(chunk_tokens[i: i + size]) for i in range(0, len(chunk_tokens), size)]

    @staticmethod
    def yield_chunks(lines_iterable, is_str=False, split_on_each_line=False):
        for chunk in Chunker._yield_chunks(lines_iterable, is_str=is_str, split_on_each_line=split_on_each_line):
            if Chunker.count_tokens(chunk) > Chunker.MAX_CHUNK_TOKENS:
                for subchunk in Chunker.split_tokens(chunk, size=Chunker.MAX_CHUNK_TOKENS - 1):
                    yield subchunk
            else:
                yield chunk

    @staticmethod
    def get_chunks(filepath, split_on_each_line=False):
        with open(filepath, 'r', encoding="utf8") as f:
            yield from Chunker.yield_chunks(f, split_on_each_line=split_on_each_line)

    @staticmethod
    def get_str_chunks(text, split_on_each_line=False):
        yield from Chunker.yield_chunks(text.split("\n"), is_str=True, split_on_each_line=split_on_each_line)




class TextToSpeechRunner:
    QUEUES = [] # TODO multiple named queues
    VLC_MEDIA_PLAYER = vlc.MediaPlayer()
    output_directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tts_output")
    lib_sounds = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib", "sounds")

    def __init__(self, model, filepath="test", overwrite=False, delete_interim_files=True, auto_play=True):
        self.speech_queue = JobQueue("Speech Queue")
        self.output_path = os.path.splitext(os.path.basename(filepath))[0]
        self.output_path_normalized = Utils.ascii_normalize(self.output_path)
        self.model = model
        self.overwrite = overwrite
        self.counter = 0
        self.audio_paths = []
        self.used_audio_paths = []
        self.delete_interim_files = delete_interim_files if auto_play else False
        self.auto_play = auto_play

    def clean(self):
        if len(self.used_audio_paths) > 0:
            def _clean(files_to_delete=[]):
                Utils.log(f"Cleaning used TTS audio files")
                fail_count = 0
                while len(files_to_delete) > 0:
                    if fail_count > 6:
                        Utils.log_red("Failed to delete audio files: " + str(len(files_to_delete)))
                        break
                    try:
                        os.remove(files_to_delete[0])
                        files_to_delete = files_to_delete[1:]
                    except Exception as e:
                        Utils.log_red(e)
                        fail_count += 1
                        time.sleep(0.5)

            Utils.start_thread(_clean, use_asyncio=False, args=[self.used_audio_paths[:]])
            self.used_audio_paths = []

    def set_output_path(self, filepath):
        self.output_path = os.path.splitext(os.path.basename(filepath))[0]
        self.output_path_normalized = Utils.ascii_normalize(self.output_path)

    def generate_output_path(self):
        output_path = os.path.join(TextToSpeechRunner.output_directory, self.output_path_normalized + str(self.counter) + ".wav")
        if self.overwrite:
            while os.path.exists(output_path):
                self.counter += 1
                output_path = os.path.join(TextToSpeechRunner.output_directory, self.output_path_normalized + str(self.counter) + ".wav")
        else:
            self.counter += 1
        return output_path

    def generate_speech_file(self, text, output_path):
        if os.path.exists(output_path) and not self.overwrite:
            Utils.log("Using existing generation file: " + output_path)
            return
        output_path1, output_path_no_unicode = self.get_output_path_no_unicode()
        final_output_path_mp3 = self.get_output_path_mp3(output_path1)
        final_output_path_mp3 = final_output_path_mp3[:-4] + " - TTS.mp3"
        if os.path.exists(final_output_path_mp3) and not self.overwrite:
            Utils.log("Using existing generation file: " + final_output_path_mp3)
            return
        Utils.log("Generating speech file: " + output_path)
        # Init TTS with the target model name
        tts = TTS(model_name=self.model[0], progress_bar=False).to(device)
        # Run TTS
        tts.tts_to_file(text=text,
                        speaker=self.model[1],
                        file_path=output_path,
                        language=self.model[2])

    def play_async(self, filepath):
        self.speech_queue.job_running = True
        TextToSpeechRunner._play(filepath)
        time.sleep(1)
        while (TextToSpeechRunner.VLC_MEDIA_PLAYER.is_playing()):
            time.sleep(.1)
        next_job_output_path = self.speech_queue.take()
        if next_job_output_path is not None and os.path.exists(next_job_output_path):
            time.sleep(2)
            Utils.start_thread(self.play_async, use_asyncio=False, args=[next_job_output_path])
        else:
            self.speech_queue.job_running = False

    def await_pending_speech_jobs(self):
        while self.speech_queue.has_pending():
            next_job_output_path = self.speech_queue.take()
            if next_job_output_path is not None:
                if os.path.exists(next_job_output_path):
                    self.play_async(next_job_output_path)
                else:
                    Utils.log_red(f"Cannot find speech output path: {next_job_output_path}")
                while self.speech_queue.job_running:
                    time.sleep(.5)
        self.clean()

    def stop_pending_jobs(self):
        if TextToSpeechRunner.VLC_MEDIA_PLAYER is not None and \
           TextToSpeechRunner.VLC_MEDIA_PLAYER.is_playing():
            TextToSpeechRunner.VLC_MEDIA_PLAYER.stop()
            TextToSpeechRunner.VLC_MEDIA_PLAYER = None

    def stop(self):
        self.stop_pending_jobs()

    @staticmethod
    def _play(filepath):
        TextToSpeechRunner.VLC_MEDIA_PLAYER = vlc.MediaPlayer(filepath)
        TextToSpeechRunner.VLC_MEDIA_PLAYER.play()

    def _speak(self, text):
        output_path = self.generate_output_path()
        self.audio_paths.append(output_path)
        self.generate_speech_file(text, output_path)
        self.add_speech_file_to_queue(output_path)

    def speak(self, text, save_mp3=False):
        for chunk in Chunker.get_str_chunks(text):
            Utils.log("-------------------\n" + chunk)
            self._speak(chunk)
        while self.speech_queue.job_running:
            time.sleep(0.5)
        self.combine_audio_files(save_mp3)

    def speak_file(self, filepath, save_mp3=True, split_on_each_line=False):
        for chunk in Chunker.get_chunks(filepath, split_on_each_line):
            Utils.log("-------------------\n" + chunk)
            self._speak(chunk)
        while self.speech_queue.job_running:
            time.sleep(0.5)
        self.combine_audio_files(save_mp3)

    def convert_to_mp3(self, file_path):
        if not os.path.exists(file_path):
            raise Exception("File not found: " + file_path)
        output_path = os.path.abspath(os.path.join(os.path.dirname(file_path), os.path.splitext(os.path.basename(file_path))[0] + '.mp3'))
        if file_path.endswith(".mp3") or os.path.exists(output_path):
            raise Exception("File already exists as mp3")
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", os.path.abspath(file_path), output_path]
        # Utils.log(args)
        try:
            completed_process = subprocess.run(args)
            if completed_process.returncode != 0:
                raise Exception()
            return output_path
        except Exception as e:
            raise Exception("Could not convert file to MP3")

    def get_output_path_no_unicode(self):
        output_path = os.path.join(TextToSpeechRunner.output_directory, self.output_path + '.wav')
        output_path_no_unicode = Utils.ascii_normalize(output_path)
        return output_path, output_path_no_unicode

    def get_output_path_mp3(self, file_path):
        return os.path.abspath(os.path.join(os.path.dirname(file_path), os.path.splitext(os.path.basename(file_path))[0] + '.mp3'))

    @staticmethod
    def get_silence_file(seconds=2):
        if type(seconds) != int or seconds < 1 or seconds > 5:
            raise Exception("Invalid number of seconds for silence: " + str(seconds))
        return os.path.join(TextToSpeechRunner.lib_sounds, "silence_" + str(seconds) + "_sec.wav")

    def combine_audio_files(self, save_mp3=False):
        output_path, output_path_no_unicode = self.get_output_path_no_unicode()
        silence_file = TextToSpeechRunner.get_silence_file(seconds=2)
        args = ["sox"]
        for i in range(len(self.audio_paths)):
            f = self.audio_paths[i]
            args.append(f.replace("\\", "/"))
            Utils.log(f"File {f} was found: {os.path.exists(f)}")
            if i < len(self.audio_paths) - 1:
                args.append(silence_file.replace("\\", "/"))
        args.append(output_path_no_unicode.replace("\\", "/"))
        # Utils.log(args)
        try:
            completed_process = subprocess.run(args)
            if completed_process.returncode == 0:
                Utils.log("Combined audio files: " + output_path)
                if save_mp3:
                    mp3_path = self.convert_to_mp3(output_path_no_unicode)
                os.remove(output_path_no_unicode)
                if self.delete_interim_files:
                    for f in self.audio_paths:
                        os.remove(f)
                else:
                    self.used_audio_paths.extend(self.audio_paths)
                self.audio_paths = []
                if save_mp3:
                    return Utils.move_file(mp3_path, output_path[:-4] + " - TTS.mp3", overwrite_existing=self.overwrite)
                else:
                    return output_path
            else:
                self.audio_paths = []
                raise Exception()
        except Exception as e:
            raise Exception("Error combining audio files")

    def add_speech_file_to_queue(self, filepath):
        if not self.auto_play or self.speech_queue.has_pending() or self.speech_queue.job_running:
            self.speech_queue.add(filepath)
        else:
            self.speech_queue.job_running = True
            Utils.start_thread(self.play_async, use_asyncio=False, args=[filepath])


def main(model, text):
    runner = TextToSpeechRunner(model)
    try:
        runner.speak(text)
    except KeyboardInterrupt:
        exit()
    while True:
        try:
            runner.speak(input())
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    # speaker = list(filter(lambda x: x if x.startswith(sys.argv[2]) else None, speakers))[0] if len(sys.argv)>2 else "Royston Min"
    # de_model = ("tts_models/de/thorsten/tacotron2-DDC", None, None)
    # multi_model = ("tts_models/multilingual/multi-dataset/xtts_v2", speaker, "en")
    # model = multi_model

    # main(model, text)

    for chunk in Chunker.get_str_chunks("""Hello and welcome to our news show! Today, we have some exciting stories for you. First up, Tesla stock jumps on Q3 earnings beat. This is a major story as investors are always looking out for the latest updates from companies in their portfolios. The live briefing by Blinken says 'more progress' from Israel needed on Gaza aid flow shows that there is still tension between Israel and Palestine, with both countries blaming each other for the lack of aid to Gaza. The North Korean troops are in Russia, would be 'legitimate targets' in Ukraine, US says is a worrying story as we don't know what the United States plans to do if Russia invades Ukraine. The DOJ warns Elon Musk's America PAC that $1 million giveaway may break the law shows that money can buy influence and the DOJ is taking action against it. The Dragon Undocks from Station, Crew-8 Heads Toward Earth is a positive story as we finally have more astronauts going to space again! Chiefs finalizing trade to get DeAndre Hopkins from Titans shows that there are still trades happening in the NFL despite COVID-19 concerns. The Israeli strikes pound Lebanese coastal city after residents evacuate is a sad story as we don't know how many people were injured or killed during the attack. Wall Street closes down, pressured by tech losses and worries about rates shows that investors are still nervous about the economy despite the new stimulus package. The McDonald's takes Quarter Pounder off the menu at 1 in 5 restaurants due to E. coli outbreak is a scary story as we don't know where it came from or how many people got sick. Olivia Munn bares mastectomy scars in new SKIMS campaign shows that celebrities are still sharing their personal stories despite the pandemic. The Troops deployed to Jewish community center in Sri Lanka surfing town after US warns of possible attack in area is a worrying story as we don't know what will happen if this attack happens. The Panthers' Young to start after Dalton hurt in crash shows that there are still injuries happening despite the new safety measures. The New guidance for stroke prevention includes Ozempic, other weight loss drugs shows that healthcare professionals are trying to find new ways to help their patients and make it easier on them. The Iranian hacker group aims at US election websites and media before vote, Microsoft says is a worrying story as we don't know how serious this attack was or if any data was compromised. At least 4 dead in 'terrorist attack' on aerospace facility in Turkey shows that there are still terrorist attacks happening despite the pandemic. The Existing home sales fall to lowest level since 2010 shows that we need more affordable housing options for people who can't afford homes right now. And finally, How long can you stand like a flamingo? The answer may reflect your age, new study says is an interesting story as it gives us something fun to think about during these difficult times."""):
        Utils.log(chunk)
