
import datetime
import os
import random
import time
import traceback

from extensions.hacker_news_souper import HackerNewsSouper
from extensions.news_api import NewsAPI
from extensions.open_weather import OpenWeatherAPI
from extensions.soup_utils import WebConnectionException
from extensions.wiki_opensearch_api import WikiOpenSearchAPI
from extensions.llm import LLM, LLMResponseException
from library_data.blacklist import blacklist, BlacklistException
from muse.muse_memory import MuseMemory
from muse.schedules_manager import SchedulesManager, ScheduledShutdownException
from muse.playback import Playback
from muse.prompter import Prompter
from muse.voice import Voice
from utils.config import config
from utils.globals import Topic
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class Muse:
    SYSTEM_LANGUAGE_NAME_IN_ENGLISH = Utils.get_english_language_name(Utils.get_default_user_language())
    enable_preparation = config.muse_config["enable_preparation"]
    preparation_starts_minutes_from_end = float(config.muse_config["preparation_starts_minutes_from_end"])
    preparation_starts_after_seconds_sleep = int(config.muse_config["preparation_starts_after_seconds_sleep"])

    def __init__(self, args, library_data):
        self.args = args
        self._schedule = SchedulesManager.default_schedule
        self.memory = MuseMemory()
        self.llm = LLM(model_name=config.llm_model_name)
        self.voice = Voice()
        self.open_weather_api = OpenWeatherAPI()
        self.news_api = NewsAPI()
        self.hacker_news_souper = HackerNewsSouper()
        self.prompter = Prompter()
        self.wiki_search = WikiOpenSearchAPI()
        self.has_started_prep = False
        self.preparation_id = None # TODO pass a prep ID along with the speech request so things can be deleted before spoke if necessary.
        self.is_cancelled_prep = False
        self.post_id = "post"
        self.prior_id = "prior"
        self.library_data = library_data
        self.get_playlist_callback = None
        if not args.placeholder:
            assert library_data is not None # The DJ should have access to the music library.

    def get_library_data(self):
        if self.library_data is None:
            raise Exception("No music library data available")
        return self.library_data

    def get_spot_profile(self, previous_track=None, track=None, last_track_failed=False, skip_track=False, old_grouping=None, new_grouping=None, grouping_type=None):
        return self.memory.get_spot_profile(previous_track, track, last_track_failed, skip_track, old_grouping, new_grouping, grouping_type)

    def set_get_playlist_callback(self, get_playlist_callback):
        self.get_playlist_callback = get_playlist_callback

    def get_playlist(self):
        if self.get_playlist_callback is None:
            raise Exception("Playlist callback was not initialized!")
        return self.get_playlist_callback()

    def say_at_some_point(self, text, spot_profile, topic):
        save_mp3 = topic is not None and topic.value in config.save_tts_output_topics
        topic_str = "" if topic is None else topic.translate().replace(" ", "_")
        if spot_profile.immediate:
            self.voice.say(text, save_mp3=save_mp3, topic=topic_str)
        else:
            self.voice.prepare_to_say(text, save_mp3=save_mp3, topic=topic_str)

    def ready_to_prepare(self, cumulative_sleep_seconds, ms_remaining):
        return Muse.enable_preparation \
            and cumulative_sleep_seconds > Muse.preparation_starts_after_seconds_sleep \
            and not self.has_started_prep \
            and ms_remaining < int(Muse.preparation_starts_minutes_from_end * 60 * 1000)

    def prepare(self, spot_profile, update_ui_callbacks=None):
        self.has_started_prep = True
        self.set_topic(spot_profile)
        if update_ui_callbacks is not None:
            if update_ui_callbacks.update_next_up_callback is not None:
                update_ui_callbacks.update_next_up_callback(spot_profile.get_upcoming_track_title())
            if update_ui_callbacks.update_prior_track_callback is not None:
                update_ui_callbacks.update_prior_track_callback(spot_profile.get_previous_track_title())
            if update_ui_callbacks.update_spot_profile_topics_text is not None:
                update_ui_callbacks.update_spot_profile_topics_text(spot_profile.get_topic_text())
        if spot_profile.is_going_to_say_something():
            Utils.log_debug(f"Preparing muse:\n{spot_profile}")
            if spot_profile.say_good_day:
                self.say_good_day()
            if not spot_profile.skip_previous_track_remark:
                self.maybe_prep_dj_post(spot_profile)
            self.maybe_prep_dj_prior(spot_profile)
            self.memory.tracks_since_last_spoke = 0
        else:
            self.memory.tracks_since_last_spoke += 1
        spot_profile.set_preparation_time()
        spot_profile.is_prepared = True

    def cancel_preparation(self, spot_profile):
        Utils.log_debug(f"Canceling muse prep:\n{spot_profile}")
        self.is_cancelled_prep = True
        if update_ui_callbacks is not None:
            if update_ui_callbacks.update_next_up_callback is not None:
                update_ui_callbacks.update_next_up_callback(spot_profile.get_upcoming_track_title())
            if update_ui_callbacks.update_prior_track_callback is not None:
                update_ui_callbacks.update_prior_track_callback(spot_profile.get_previous_track_title())
            if update_ui_callbacks.update_spot_profile_topics_text is not None:
                update_ui_callbacks.update_spot_profile_topics_text(spot_profile.get_topic_text())

    def maybe_dj(self, spot_profile):
        # TODO quality info for songs
        start = time.time()
        self.voice.finish_speaking()
        while not spot_profile.is_prepared:
            time.sleep(1)
            self.voice.finish_speaking()
        return round(time.time() - start)

    def reset(self):
        self.has_started_prep = False
        self.is_cancelled_prep = False
        self.check_schedules()

    def check_schedules(self):
        self.check_for_shutdowns()
        if not self.args.muse:
            return
        now = datetime.datetime.now()
        active_schedule = SchedulesManager.get_active_schedule(now)
        if active_schedule is None:
            raise Exception("Failed to establish active schedule")
        if self._schedule != active_schedule:
            Utils.log_yellow(f"Switching DJ to {active_schedule.voice} from {self._schedule.voice} - until {active_schedule.next_end(now)}")
            self.change_voice(active_schedule.voice)
        else:
            Utils.log("No change in schedule")
        self._schedule = active_schedule

    def change_voice(self, voice_name):
        self.voice = Voice(voice_name)
        self.voice.prepare_to_say(_("Hello, I'm {0}").format(voice_name))

    def check_for_shutdowns(self):
        now = datetime.datetime.now()
        try:
            SchedulesManager.check_for_shutdown_request(now)
        except ScheduledShutdownException as e:
            if self.args.muse:
                self.sign_off(now)
            raise e

    def sign_off(self, now):
        now_general_word = _("tonight") if (now.hour < 5 or now.hour > 19) else _("today")
        tomorrow = SchedulesManager.get_tomorrow(now)
        self.voice.prepare_to_say(_("The scheduled shutdown time has arrived. That's it for {0}.").format(now_general_word))
        tomorrow_schedule = SchedulesManager.get_active_schedule(tomorrow)
        if tomorrow_schedule is not None:
            if tomorrow_schedule.voice == self._schedule.voice:
                self.voice.prepare_to_say(_("I'll be on again tomorrow."))
            else:
                self.voice.prepare_to_say(_("Tomorrow you'll hear from {0}.").format(tomorrow_schedule.voice))
                next_weekday_for_this_voice = SchedulesManager.get_next_weekday_index_for_voice(self._schedule.voice, tomorrow)
                if next_weekday_for_this_voice is not None:
                    if next_weekday_for_this_voice == now.weekday():
                        self.voice.prepare_to_say(_("The next time I'll be on is next week, at the same time."))
                    elif len(self._schedule.weekday_options) < 7:
                        self.voice.prepare_to_say(_("I'll be on again this coming {0}.").format(I18N.day_of_the_week(next_weekday_for_this_voice)))
        self.voice.finish_speaking()
        self._schedule = tomorrow_schedule

    def say_good_day(self):
        hour = SchedulesManager.get_hour()
        if hour < 5 or hour > 22:
            return
        Utils.log_debug("Saying good day")
        if hour < 11:
            self.voice.prepare_to_say(_("Good morning"))
        elif hour < 13:
            self.voice.prepare_to_say(_("Good day"))
        elif hour < 17:
            self.voice.prepare_to_say(_("Good afternoon"))
        else:
            self.voice.prepare_to_say(_("Good evening"))

    def maybe_prep_dj_post(self, spot_profile):
        # TODO quality info for songs
        if spot_profile.speak_about_prior_track:
            self.speak_about_previous_track(spot_profile)
        if spot_profile.speak_about_prior_group:
            self.speak_about_previous_group(spot_profile)

    # def maybe_dj_post(self, spot_profile):
    #     # Release lock on TTS runner for "post" queue
    #     if spot_profile.skip_previous_track_remark:
    #         # TODO cancel the pending "post" queue
    #         return
    #     pass

    def speak_about_previous_track(self, spot_profile):
        # TODO have muse mention if the track has been split in the spot.
        previous_track = spot_profile.previous_track
        dj_remark = _("That was \"{0}\" in \"{1}\"").format(previous_track.readable_title(), previous_track.readable_album())
        if previous_track.artist is not None and previous_track.artist!= "" and random.random() < 0.8:
            dj_remark += _(" by \"{0}\".").format(previous_track.readable_artist())
        else:
            dj_remark += "."
        if previous_track._is_extended and random.random() < 0.8:
            if random.random() < 0.5:
                dj_remark +=  " " + _("That was a new track. How'd you like that?")
            else:
                dj_remark = _("That was a new one. How'd you like it?") + " " + dj_remark
        self.say_at_some_point(dj_remark, spot_profile, None)

    def maybe_prep_dj_prior(self, spot_profile):
        # TODO quality info for songs
        if spot_profile.speak_about_upcoming_group:
            self.speak_about_upcoming_group(spot_profile)
            spot_profile.has_already_spoken = True
        if spot_profile.speak_about_upcoming_track:
            self.speak_about_upcoming_track(spot_profile)
            spot_profile.has_already_spoken = True
        if spot_profile.talk_about_something:
            self.talk_about_something(spot_profile)
        else:
            self.memory.tracks_since_last_topic += 1

    def speak_about_upcoming_track(self, spot_profile):
        # TODO have muse mention if the track has been split in the spot.
        track = spot_profile.track
        if spot_profile.previous_track is None:
            dj_remark = _("To start, we'll be playing: \"{0}\" from \"{1}\"").format(track.readable_title(), track.readable_album())
        else:
            dj_remark = _("Next up, we'll be playing: \"{0}\" from \"{1}\"").format(track.readable_title(), track.readable_album())
        if track.artist is not None and track.artist!= "":
            dj_remark += _(" by \"{0}\".").format(track.readable_artist())
        else:
            dj_remark += "."
        if track._is_extended and random.random() < 0.8:
            dj_remark += " " + _("This one is a new track.")
        self.say_at_some_point(dj_remark, spot_profile, None)

    def speak_about_previous_group(self, spot_profile):
        previous_group = spot_profile.old_grouping
        if spot_profile.previous_track is not None:
            group_count = self.get_playlist().get_group_count(previous_group)
            if group_count > 1:
                if spot_profile.previous_track._is_extended:
                    dj_remark = _("After that short interlude, we're back to our {0} shuffle.").format(
                        spot_profile.grouping_type.get_grouping_readable_name())
                else:
                    dj_remark = _("We've been listening to a group of tracks from the {0} {1}").format(
                        spot_profile.grouping_type.get_grouping_readable_name(), previous_group)
                self.say_at_some_point(dj_remark, spot_profile, None)

    def speak_about_upcoming_group(self, spot_profile):
        new_group = spot_profile.new_grouping
        if spot_profile.previous_track is not None and spot_profile.track is not None:
            group_count = self.get_playlist().get_group_count(new_group)
            if group_count > 1:
                if spot_profile.previous_track._is_extended:
                    dj_remark = _("We're listening to a group of tracks from the {0} {1}.").format(
                        spot_profile.grouping_type.get_grouping_readable_name(), new_group)
                else:
                    dj_remark = _("We're going to start a new group of tracks from the {0} {1}.").format(
                        spot_profile.grouping_type.get_grouping_readable_name(), new_group)
                self.say_at_some_point(dj_remark, spot_profile, None)

    def get_topic(self, previous_track, excluded_topics=[]):
        excluded_topics = list(excluded_topics)
        if Prompter.over_n_hours_since_last(Topic.WEATHER, n_hours=24) and not self.memory.is_recent_topics(["news", "hackernews"], n=3):
            topic = Topic.WEATHER
        elif Prompter.over_n_hours_since_last(Topic.NEWS, n_hours=96) and not self.memory.is_recent_topics(["weather", "hackernews"], n=3):
            topic = Topic.NEWS
        elif Prompter.over_n_hours_since_last(Topic.HACKERNEWS, n_hours=96) and not self.memory.is_recent_topics(["weather", "news"], n=3):
            topic = Topic.HACKERNEWS
        else:
            topic = Prompter.get_oldest_topic(excluded_topics=excluded_topics)

        if topic not in excluded_topics:
            if topic in [Topic.HACKERNEWS, Topic.NEWS] and Prompter.under_n_hours_since_last(topic, n_hours=14):
                excluded_topics.append(topic)
            if previous_track is None and topic == Topic.TRACK_CONTEXT_POST:
                excluded_topics.append(topic)

        while topic in excluded_topics:
            topic = self.get_topic(previous_track, excluded_topics=excluded_topics)

        return topic

    def set_topic(self, spot_profile):
        spot_profile.topic = self.get_topic(spot_profile.previous_track)
        spot_profile.topic_translated = spot_profile.topic.translate()

    def talk_about_something(self, spot_profile):
        self.memory.tracks_since_last_topic = 0

        if (spot_profile.has_already_spoken and random.random() < 0.75) \
                or (not spot_profile.has_already_spoken and random.random() < 0.6):
            if not spot_profile.has_already_spoken:
                remark = _("First let's hear about {0}").format(spot_profile.topic_translated)
            else:
                remark = _("But first, let's hear about {0}.").format(spot_profile.topic_translated)
            self.say_at_some_point(remark, spot_profile, None)

        topic = spot_profile.topic
        Utils.log(f"Talking about topic: {topic.value}")

        func = None
        args = [spot_profile]
        kwargs = {}

        if topic == Topic.WEATHER:
            func = self.talk_about_weather
            args = [config.open_weather_city, spot_profile]
        elif topic in [Topic.NEWS, Topic.HACKERNEWS]:
            func = self.talk_about_news
            args = [topic, spot_profile]
        elif topic == Topic.JOKE:
            func = self.tell_a_joke
        elif topic == Topic.FACT:
            func = self.share_a_fact
        elif topic == Topic.TRUTH_AND_LIE:
            func = self.play_two_truths_and_one_lie
        elif topic == Topic.FABLE:
            func = self.share_a_fable
        elif topic == Topic.APHORISM:
            func = self.share_an_aphorism
        elif topic == Topic.POEM:
            func = self.share_a_poem
        elif topic == Topic.QUOTE:
            func = self.share_a_quote
        elif topic == Topic.TONGUE_TWISTER:
            func = self.share_a_tongue_twister
        elif topic == Topic.CALENDAR:
            func = self.talk_about_the_calendar
        elif topic == Topic.MOTIVATION:
            func = self.share_a_motivational_message
        elif topic == Topic.TRACK_CONTEXT_PRIOR:
            func = self.talk_about_track_context
            args = [spot_profile.track, spot_profile, Topic.TRACK_CONTEXT_PRIOR]
        elif topic == Topic.TRACK_CONTEXT_POST:
            func = self.talk_about_track_context
            args = [spot_profile.previous_track, spot_profile, Topic.TRACK_CONTEXT_POST]
        elif topic == Topic.RANDOM_WIKI_ARTICLE:
            func = self.talk_about_random_wiki_article
        elif topic == Topic.FUNNY_STORY:
            func = self.share_a_funny_story
        elif topic == Topic.LANGUAGE_LEARNING:
            func = self.teach_language
        else:
            Utils.log_yellow(f"Unhandled topic: {topic}")
            return

        self._wrap_function(spot_profile, topic, func, args, kwargs)

    def talk_about_weather(self, city="Washington", spot_profile=None):
        weather = self.open_weather_api.get_weather_for_city(city)
        weather_summary = self.generate_text(
            self.get_prompt(Topic.WEATHER) + city + ":\n\n" + str(weather))
        self.say_at_some_point(weather_summary, spot_profile, Topic.WEATHER)

    def talk_about_news(self, topic=None, spot_profile=None):
        if topic == Topic.HACKERNEWS:
            news = self.hacker_news_souper.get_news(total=15)
        else:
            news = self.news_api.get_news(topic=topic)
        news_summary = self.generate_text(
            self.get_prompt(topic) + "\n\n" + str(news))
        self.say_at_some_point(news_summary, spot_profile, topic)

    def tell_a_joke(self, spot_profile):
        joke = self.generate_text(self.get_prompt(Topic.JOKE))
        self.say_at_some_point(joke, spot_profile, Topic.JOKE)

    def share_a_fact(self, spot_profile):
        fact = self.generate_text(self.get_prompt(Topic.FACT))
        self.say_at_some_point(fact, spot_profile, Topic.FACT)

    def play_two_truths_and_one_lie(self, spot_profile):
        resp = self.generate_text(self.get_prompt(Topic.TRUTH_AND_LIE))
        self.say_at_some_point(resp, spot_profile, Topic.TRUTH_AND_LIE)

    def share_a_fable(self, spot_profile):
        fable = self.generate_text(self.get_prompt(Topic.FABLE))
        self.say_at_some_point(fable, spot_profile, Topic.FABLE)

    def share_an_aphorism(self, spot_profile):
        aphorism = self.generate_text(self.get_prompt(Topic.APHORISM))
        self.say_at_some_point(aphorism, spot_profile, Topic.APHORISM)

    def share_a_poem(self, spot_profile):
        poem = self.generate_text(self.get_prompt(Topic.POEM))
        self.say_at_some_point(poem, spot_profile, Topic.POEM)
    
    def share_a_quote(self, spot_profile):
        quote = self.generate_text(self.get_prompt(Topic.QUOTE))
        self.say_at_some_point(quote, spot_profile, Topic.QUOTE)

    def share_a_tongue_twister(self, spot_profile):
        if config.tongue_twisters_dir is None or config.tongue_twisters_dir == "":
            raise Exception("No tongue twister directory specified")
        Utils.log(f"Playing tongue twister from {config.tongue_twisters_dir}")
        playback = Playback.new_playback(config.tongue_twisters_dir, self.get_library_data().data_callbacks)
        tongue_twister_track, __, ___ = playback._playback_config.next_track()
        if tongue_twister_track is None or not os.path.exists(tongue_twister_track.filepath):
            raise Exception(f"Invalid tongue twister file: {tongue_twister_track}")
        Prompter.update_history(spot_profile.topic)
        self.voice.add_speech_file_to_queue(tongue_twister_track.filepath)

    def talk_about_the_calendar(self, spot_profile):
        # TODO talk about tomorrow as well, or the upcoming week
        today = datetime.datetime.today()
        prompt = self.get_prompt(Topic.CALENDAR)
        prompt = prompt.replace("{DATE}", today.strftime("%A %B %d %Y"))
        prompt = prompt.replace("{TIME}", today.strftime("%H:%M"))
        calendar = self.generate_text(prompt)
        self.say_at_some_point(calendar, spot_profile, Topic.CALENDAR)

    def share_a_motivational_message(self, spot_profile):
        motivation = self.generate_text(self.get_prompt(Topic.MOTIVATION))
        self.say_at_some_point(motivation, spot_profile, Topic.MOTIVATION)

    def talk_about_track_context(self, track, spot_profile, topic):
        if spot_profile.track is None or spot_profile.topic is None or topic is None:
            raise Exception("No track or topic specified")
        prompt = self.get_prompt(topic)
        prompt = prompt.replace("{TRACK_DETAILS}", track.get_track_details())
        track_context = self.generate_text(prompt)
        self.say_at_some_point(track_context, spot_profile, None)

    def talk_about_random_wiki_article(self, spot_profile):
        article_blacklisted = True
        blacklisted_words_found = set()
        count = 0
        while article_blacklisted:
            article = self.wiki_search.random_wiki()
            if article is None or not article.is_valid():
                raise Exception("No valid wiki article found")
            article_text = str(article)[:2000]
            blacklist_words = blacklist.test_all(article_text)
            blacklisted_words_found.update(blacklist_words)
            article_blacklisted = len(blacklist_words) > 0
            if count > 10:
                raise Exception(f"No valid wiki article found after 10 tries. Blacklisted words: {blacklisted_words_found}")
            count += 1
        prompt = self.get_prompt(Topic.RANDOM_WIKI_ARTICLE)
        prompt = prompt.replace("{ARTICLE}", str(article)[:2000])
        summary = self.generate_text(prompt)
        self.say_at_some_point(summary, spot_profile, Topic.RANDOM_WIKI_ARTICLE)

    def share_a_funny_story(self, spot_profile):
        funny_story = self.generate_text(self.get_prompt(Topic.FUNNY_STORY))
        self.say_at_some_point(funny_story, spot_profile, Topic.FUNNY_STORY)

    def teach_language(self, spot_profile):
        prompt = self.get_prompt(Topic.LANGUAGE_LEARNING)
        prompt = prompt.replace("{LANGUAGE}", config.muse_language_learning_language)
        if config.muse_language_learning_language_level is not None and config.muse_language_learning_language_level.strip() != "":
            prompt = prompt.replace("{LEVEL}", config.muse_language_learning_language_level)
        else:
            prompt = prompt.replace("{LEVEL}", "basic")
        language_response = self.generate_text(prompt)
        self.say_at_some_point(language_response, spot_profile, Topic.LANGUAGE_LEARNING)

    def start_extensions_thread(self, initial_sleep=True, overwrite_cache=False):
        self.get_library_data().start_extensions_thread(initial_sleep=initial_sleep, overwrite_cache=overwrite_cache, voice=self.voice)

    def get_prompt(self, topic):
        prompt = self.prompter.get_prompt(topic)
        if not self.args.use_system_language_for_all_topics:
            return prompt
        if topic == Topic.LANGUAGE_LEARNING and Muse.SYSTEM_LANGUAGE_NAME_IN_ENGLISH == config.muse_language_learning_language:
            # Don't replace the whole prompt, it would be trying to teach the same language the prompt is already in.
            return prompt
        language_code = Utils.get_default_user_language()
        if language_code == "en" or language_code not in ["de", "es", "fr", "it"]:
            Utils.log(f"No translation available for language {language_code} topic {topic}, using English")
            return prompt
        try:
            translation_prompt = self.prompter.get_translation_prompt(language_code, Muse.SYSTEM_LANGUAGE_NAME_IN_ENGLISH, prompt)
            prompt = self.generate_text(translation_prompt, json_key="prompt")
        except Exception as e:
            Utils.log(f"Failed to translate prompt for topic {topic} into language {Muse.SYSTEM_LANGUAGE_NAME_IN_ENGLISH} with error: {e}")
        return prompt

    def generate_text(self, prompt, json_key=None):
        prompt_text_to_test = prompt
        variant_part_marker = "Please give your summary after the provided articles below."
        if variant_part_marker in prompt_text_to_test:
            prompt_text_to_test = prompt_text_to_test[prompt_text_to_test.index(variant_part_marker):]
            prompt_text_to_test = prompt_text_to_test[prompt_text_to_test.index("\n") + 1:]
        blacklisted_items_in_prompt = blacklist.test_all(prompt_text_to_test)
        text = self.llm.ask(prompt, json_key=json_key)
        generations = []
        all_blacklist_items = set()
        blacklist_items = blacklist.test_all(text, excluded_items=blacklisted_items_in_prompt)
        attempts = 0
        while len(blacklist_items) > 0:
            blacklist_items_str = ", ".join(sorted([str(i) for i in all_blacklist_items]))
            Utils.log("Hit blacklisted items: " + blacklist_items_str)
            Utils.log("Text: " + text)
            all_blacklist_items.update(set(blacklist_items))
            text = self.llm.ask(prompt, json_key=json_key)
            generations.append(text)
            blacklist_items = blacklist.test_all(text, excluded_items=blacklisted_items_in_prompt)
            attempts += 1
            if attempts > 10:
                blacklist_items_str = ", ".join(sorted([str(i) for i in all_blacklist_items]))
                texts_str = "\n".join(generations)
                raise BlacklistException(f"Failed to generate text - blacklist items found: {blacklist_items_str}\n{texts_str}")
        return text

    def _wrap_function(self, spot_profile, topic, func, _args=[], _kwargs={}):
        try:
            return func(*_args, **_kwargs)
        except WebConnectionException as e:
            Utils.log_red(e)
            self.say_at_some_point(_("We're having some technical difficulties in accessing our source for {0}. We'll try again later").format(topic),
                                   spot_profile, None)
        except LLMResponseException as e:
            Utils.log_red(e)
            self.say_at_some_point(_("It seems our writer for {0} is unexpectedly away at the moment. Did we forget to pay his salary again?").format(topic),
                                   spot_profile, None)
        except BlacklistException as e:
            Utils.log_red(e)
            self.say_at_some_point(_("We've found problems with all of our {0} ideas. Please try again later.").format(topic),
                                   spot_profile, None)
        except Exception as e:
            Utils.log_red(e)
            traceback.print_exc()
            self.say_at_some_point(_("Something went wrong. We'll try to fix it soon."), spot_profile, None)



