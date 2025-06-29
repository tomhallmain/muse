from dataclasses import dataclass
from datetime import datetime
import os
import subprocess
import sys
import time
from typing import Optional, Callable
import uuid

import torch
import music_tag

from utils.config import config
from utils.job_queue import JobQueue
from utils.logging_setup import get_logger
from utils.utils import Utils

try:
    sys.path.insert(0, config.coqui_tts_location)
    from TTS.api import TTS
    # Utils.remove_extra_handlers()
except ImportError:
    raise Exception("Failed to import Coqui TTS. Ensure the code is downloaded and the \"coqui_tts_location\" value is set in the config.")

import vlc

# from ops.speakers import speakers
from tts.chunker import Chunker
from utils.config import config
from utils.job_queue import JobQueue
from utils.utils import Utils

# Get device
device = "cuda" if torch.cuda.is_available() else "cpu"

# List available 🐸TTS models
# pprint.pprint(TTS().list_models())

# Get logger for this module
logger = get_logger(__name__)

@dataclass
class TTSConfig:
    """Configuration for TextToSpeechRunner and related classes."""
    model: str
    filepath: str = "test"
    overwrite: bool = False
    delete_interim_files: bool = True
    auto_play: bool = True
    run_context: Optional[object] = None
    skip_cjk: bool = True
    skip_redundant: bool = True

class TTSSpeakInvocation:
    _tracking = {}  # Maps invocation_id to TTSSpeakInvocation

    @classmethod
    def create(cls, speak_callback, config):
        """Create a new invocation with a unique ID."""
        return cls(str(uuid.uuid4()), speak_callback, config)

    def __init__(self, invocation_id: str, speak_callback: Callable, config: TTSConfig):
        self.invocation_id = invocation_id
        self.error_count = 0
        self.total_chunks = 0
        self.chunker = Chunker(skip_cjk=config.skip_cjk, skip_redundant=config.skip_redundant)
        self.speak_callback = speak_callback
        self.config = config  # Store config to access run_context
        self._tracking[invocation_id] = self

    def increment_error(self):
        self.error_count += 1

    def increment_chunks(self):
        self.total_chunks += 1

    def all_chunks_failed(self) -> bool:
        return self.error_count > 0 and self.error_count == self.total_chunks

    def _process_chunks(self, chunks):
        """
        Process chunks through the chunker and generate speech for each chunk.
        
        Args:
            chunks: Iterable of text chunks to process
            
        Returns:
            str: The full processed text
        """
        full_text = ""
        for chunk in chunks:
            # Check for skip before processing each chunk
            if self.config.run_context and self.config.run_context.should_skip():
                logger.info("Skipping remaining TTS chunks due to skip request")
                break
                
            logger.info("-------------------\n" + chunk)
            if full_text:
                full_text += "\n\n"
            full_text += chunk
            self.increment_chunks()
            self.speak_callback(chunk, self)
            
        if self.all_chunks_failed():
            raise Exception(f"All {self.total_chunks} chunks failed to generate speech")
            
        return full_text

    def process_text(self, text, locale=None):
        """
        Process text through the chunker and generate speech for each chunk.
        
        Args:
            text: The text to process
            locale: Optional locale for text processing
            
        Returns:
            str: The full processed text
        """
        if not text or not text.strip():
            raise Exception("Empty text provided to process")
            
        return self._process_chunks(
            self.chunker.get_str_chunks(text, locale=locale)
        )

    def process_file(self, filepath, split_on_each_line=False, locale=None):
        """
        Process a file through the chunker and generate speech for each chunk.
        
        Args:
            filepath: Path to the file to process
            split_on_each_line: Whether to split on each line
            locale: Optional locale for text processing
            
        Returns:
            str: The full processed text
        """
        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            raise Exception("Empty or non-existent file provided to process")
            
        return self._process_chunks(
            self.chunker.get_chunks(filepath, split_on_each_line, locale=locale)
        )

    def cleanup(self):
        if self.invocation_id in self._tracking:
            del self._tracking[self.invocation_id]

class TextToSpeechRunner:
    QUEUES = [] # TODO multiple named queues
    VLC_MEDIA_PLAYER = vlc.MediaPlayer()
    output_directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tts_output")
    lib_sounds = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib", "sounds")

    def __init__(self, config: TTSConfig):
        self.config = config
        # WARNING: The speech queue is shared across all TTSRunner instances.
        # When skip is triggered, it will cancel ALL pending speech jobs, not just
        # the current one. This means if multiple TTS invocations are running
        # simultaneously (e.g. from different parts of the application), they will
        # all be cancelled when skip is pressed. This is currently acceptable since
        # the DJ's speech is supplementary to the music experience, but this should
        # be reviewed if more critical TTS functionality is added in the future.
        self.speech_queue = JobQueue("Speech Queue")
        self.output_path = os.path.splitext(os.path.basename(config.filepath))[0]
        self.output_path_normalized = Utils.ascii_normalize(self.output_path)
        self.model = config.model
        self.overwrite = config.overwrite
        self.counter = 0
        self.audio_paths = []
        self.used_audio_paths = []
        self.delete_interim_files = config.delete_interim_files if config.auto_play else False
        self.auto_play = config.auto_play
        self.run_context = config.run_context

    def clean(self):
        if len(self.used_audio_paths) > 0:
            def _clean(files_to_delete=[]):
                logger.info(f"Cleaning used TTS audio files")
                fail_count = 0
                while len(files_to_delete) > 0:
                    if fail_count > 6:
                        logger.error("Failed to delete audio files: " + str(len(files_to_delete)))
                        break
                    try:
                        os.remove(files_to_delete[0])
                        files_to_delete = files_to_delete[1:]
                    except Exception as e:
                        logger.error(e)
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
            logger.info("Using existing generation file: " + output_path)
            return
        output_path1, output_path_no_unicode = self.get_output_path_no_unicode()
        final_output_path_mp3 = self.get_output_path_mp3(output_path1)
        final_output_path_mp3 = final_output_path_mp3[:-4] + " - TTS.mp3"
        if os.path.exists(final_output_path_mp3) and not self.overwrite:
            logger.info("Using existing generation file: " + final_output_path_mp3)
            return
        logger.info("Generating speech file: " + output_path)
        try:
            # Init TTS with the target model name
            tts = TTS(model_name=self.model[0], progress_bar=False).to(device)
            # Run TTS with error handling
            try:
                tts.tts_to_file(text=text,
                              speaker=self.model[1],
                              file_path=output_path,
                              language=self.model[2])
            except Exception as e:
                logger.error(f"TTS generation failed: {str(e)}")
                # Check if the file was created despite the error
                if not os.path.exists(output_path):
                    raise Exception("TTS failed to generate audio file")
                # If file exists, we can continue despite the error
                logger.info("TTS generated file despite error, continuing...")
        except Exception as e:
            logger.error(f"TTS initialization failed: {str(e)}")
            raise

    def play_async(self, filepath):
        if self.run_context and self.run_context.should_skip():
            return
        self.speech_queue.job_running = True
        TextToSpeechRunner._play(filepath)
        time.sleep(1)
        while (TextToSpeechRunner.VLC_MEDIA_PLAYER.is_playing()):
            if self.run_context and self.run_context.should_skip():
                return
            time.sleep(.1)
        next_job_output_path = self.speech_queue.take()
        if next_job_output_path is not None and os.path.exists(next_job_output_path):
            time.sleep(2)
            Utils.start_thread(self.play_async, use_asyncio=False, args=[next_job_output_path])
        else:
            self.speech_queue.job_running = False

    def await_pending_speech_jobs(self, run_jobs=True):
        if self.run_context and self.run_context.should_skip():
            return
        if run_jobs:
            while self.speech_queue.has_pending():
                next_job_output_path = self.speech_queue.take()
                if next_job_output_path is not None:
                    if os.path.exists(next_job_output_path):
                        self.play_async(next_job_output_path)
                    else:
                        logger.error(f"Cannot find speech output path: {next_job_output_path}")
                    while self.speech_queue.job_running:
                        time.sleep(.5)
            self.clean()
        else:
            while self.speech_queue.has_pending():
                time.sleep(.5)
            while self.speech_queue.job_running:
                time.sleep(.5)

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

    def _speak(self, text, invocation: TTSSpeakInvocation):
        output_path = self.generate_output_path()
        try:
            self.generate_speech_file(text, output_path)
            self.audio_paths.append(output_path)
            self.add_speech_file_to_queue(output_path)
        except Exception as e:
            invocation.increment_error()
            logger.error(f"TTS generation error: {str(e)}")
            # Clean up the output file if it was created
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except:
                    pass

    def speak(self, text, save_mp3=False, locale=None):
        if self.run_context and self.run_context.should_skip():
            # Clear the speech queue when skipping
            return self.speech_queue.cancel()
            
        invocation = TTSSpeakInvocation.create(self._speak, self.config)
        
        try:
            full_text = invocation.process_text(text, locale)
            
            while self.speech_queue.job_running:
                if self.run_context and self.run_context.should_skip():
                    # Clear the speech queue when skipping
                    return self.speech_queue.cancel()
                time.sleep(0.5)
            return self.combine_audio_files(save_mp3, text_content=full_text)
        finally:
            invocation.cleanup()

    def speak_file(self, filepath, save_mp3=True, split_on_each_line=False, locale=None):
        if self.run_context and self.run_context.should_skip():
            return self.speech_queue.cancel()
            
        invocation = TTSSpeakInvocation.create(self._speak, self.config)
        
        try:
            full_text = invocation.process_file(filepath, split_on_each_line, locale)
            
            while self.speech_queue.job_running:
                if self.run_context and self.run_context.should_skip():
                    return self.speech_queue.cancel()
                time.sleep(0.5)
            return self.combine_audio_files(save_mp3, text_content=full_text)
        finally:
            invocation.cleanup()

    def convert_to_mp3(self, file_path, text_content=None):
        if not os.path.exists(file_path):
            raise Exception("File not found: " + file_path)
        output_path = os.path.abspath(os.path.join(os.path.dirname(file_path), os.path.splitext(os.path.basename(file_path))[0] + '.mp3'))
        if file_path.endswith(".mp3") or os.path.exists(output_path):
            raise Exception("File already exists as mp3")
        args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", os.path.abspath(file_path), output_path]
        # logger.info(args)
        try:
            completed_process = subprocess.run(args)
            if completed_process.returncode != 0:
                raise Exception()
            self.add_metadata(output_path, text_content)
            return output_path
        except Exception as e:
            raise Exception("Could not convert file to MP3: " + str(e))

    def add_metadata(self, output_path, text_content):
        # Add metadata if the MP3 file was successfully created
        try:
            f = music_tag.load_file(output_path)
            
            # Basic track info
            if text_content and text_content.strip() != "":
                f['lyrics'] = text_content
                # Use first line of text as title if available
                first_line = text_content.split('\n')[0][:50]  # Limit length for title
                f['tracktitle'] = first_line
            else:
                f['tracktitle'] = "Unknown"
            
            # Artist and source info
            speaker_name = self.model[1] if self.model[1] else "Unknown Speaker"
            f['artist'] = f"{speaker_name} (CoquiAI)"
            f['album'] = "Muse app output"
            
            # Additional metadata for identification
            f['albumartist'] = "CoquiAI TTS"
            f['genre'] = "Text-to-Speech"
            f['comment'] = f"Generated using CoquiAI TTS model: {self.model[0]}"
            if self.model[2]:  # If language is specified
                f['comment'] = f"{f['comment']} (Language: {self.model[2]})"

            f['year'] = datetime.now().year
            f.save()
            logger.info(f"Added metadata to {output_path}")
        except Exception as e:
            logger.warning(f"Could not add metadata: {e}")

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

    def combine_audio_files(self, save_mp3=False, text_content=None):
        output_path, output_path_no_unicode = self.get_output_path_no_unicode()
        silence_file = TextToSpeechRunner.get_silence_file(seconds=2)
        args = ["sox"]
        for i in range(len(self.audio_paths)):
            f = self.audio_paths[i]
            args.append(f.replace("\\", "/"))
            logger.info(f"File {f} was found: {os.path.exists(f)}")
            if i < len(self.audio_paths) - 1:
                args.append(silence_file.replace("\\", "/"))
        args.append(output_path_no_unicode.replace("\\", "/"))
        # logger.info(args)
        try:
            completed_process = subprocess.run(args)
            if completed_process.returncode == 0:
                logger.info("Combined audio files: " + output_path)
                if save_mp3:
                    mp3_path = self.convert_to_mp3(output_path_no_unicode, text_content=text_content)
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
    config = TTSConfig(model=model)
    runner = TextToSpeechRunner(config)
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
    speaker = list(filter(lambda x: x if x.startswith(sys.argv[2]) else None, speakers))[0] if len(sys.argv)>2 else "Royston Min"
    de_model = ("tts_models/de/thorsten/tacotron2-DDC", None, None)
    multi_model = ("tts_models/multilingual/multi-dataset/xtts_v2", speaker, "en")
    model = multi_model
    text = ""

    main(model, text)

    # for chunk in Chunker.get_str_chunks(""""""):
    #     logger.info(chunk)
