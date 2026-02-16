import datetime
import os
import random
import time
import traceback
from typing import Optional, List, Callable

from extensions.hacker_news_souper import HackerNewsSouper
from extensions.news_api import NewsAPI
from extensions.open_weather import OpenWeatherAPI
from extensions.soup_utils import WebConnectionException
from extensions.wiki_opensearch_api import WikiOpenSearchAPI
from extensions.llm import LLM, LLMResponseException, LLMResult
from library_data.blacklist import Blacklist, BlacklistException
from library_data.media_track import MediaTrack
from muse.dj_persona import DJPersona
from muse.muse_memory import muse_memory
from muse.schedules_manager import SchedulesManager, ScheduledShutdownException
from muse.playback import Playback
from muse.prompter import Prompter
from muse.voice import Voice
from utils.config import config
from utils.globals import Topic, IntroType, Globals
from utils.logging_setup import get_logger
from utils.translations import I18N, SUPPORTED_LANGUAGE_CODES
from utils.utils import Utils

_ = I18N._

# Get logger for this module
logger = get_logger(__name__)

class Muse:
    SYSTEM_LANGUAGE_NAME_IN_ENGLISH = Utils.get_english_language_name(Utils.get_default_user_language())
    enable_preparation = config.muse_config[Globals.ConfigKeys.ENABLE_PREPARATION]
    preparation_starts_minutes_from_end = float(config.muse_config[Globals.ConfigKeys.PREPARATION_STARTS_MINUTES_FROM_END])
    preparation_starts_after_seconds_sleep = int(config.muse_config[Globals.ConfigKeys.PREPARATION_STARTS_AFTER_SECONDS_SLEEP])

    def __init__(self, args, library_data, run_context, ui_callbacks=None):
        self.args = args
        self.library_data = library_data
        self._run_context = run_context
        self.ui_callbacks = ui_callbacks
        if not args.placeholder:
            assert self.library_data is not None # The DJ should have access to the music library.
            assert self._run_context is not None

        self._schedule = SchedulesManager.default_schedule
        if self._schedule is None:
            raise Exception("Failed to establish active schedule")
        self.memory = muse_memory
        self.llm = LLM(model_name=config.llm_model_name)
        
        initial_voice = self._schedule.voice
        persona = self.memory.get_persona_manager().get_persona(initial_voice)

        # Update UI with nothing, the actual persona will be set based on the result of check_schedules
        if self.ui_callbacks and self.ui_callbacks.update_dj_persona_callback is not None:
            self.ui_callbacks.update_dj_persona_callback("")

        if persona:
            self.memory.get_persona_manager().set_current_persona(persona.voice_name)
            self.voice = Voice(persona.voice_name, run_context=self._run_context)
            self.wiki_search = WikiOpenSearchAPI(language_code=persona.language_code)
        else:
            self.voice = Voice(initial_voice, run_context=self._run_context)
            self.wiki_search = WikiOpenSearchAPI(language_code=Utils.get_default_user_language())
            
        self.open_weather_api = OpenWeatherAPI()
        self.news_api = NewsAPI()
        self.hacker_news_souper = HackerNewsSouper()
        self.prompter = Prompter()
        self.has_started_prep = False
        self.preparation_id = None # TODO pass a prep ID along with the speech request so things can be deleted before spoke if necessary.
        self.is_cancelled_prep = False
        self.post_id = "post"
        self.prior_id = "prior"
        self.get_playlist_callback = None
        self._last_checked_schedules = None

    def get_library_data(self):
        if self.library_data is None:
            raise Exception("No music library data available")
        return self.library_data

    def get_spot_profile(self, previous_track=None, track_result=None, last_track_failed=False, skip_track=False,
                         grouping_type=None, get_upcoming_tracks_callback=None):
        return self.memory.get_spot_profile(previous_track, track_result, last_track_failed, skip_track,
                                            grouping_type, get_upcoming_tracks_callback)

    def set_get_playlist_callback(self, get_playlist_callback):
        self.get_playlist_callback = get_playlist_callback

    def get_playlist(self):
        if self.get_playlist_callback is None:
            raise Exception("Playlist callback was not initialized!")
        return self.get_playlist_callback()

    def get_current_persona(self):
        return self.memory.get_persona_manager().get_current_persona()

    def get_locale(self, locale: Optional[str] = None):
        if locale is not None:
            return locale
        persona = self.get_current_persona()
        if persona is not None:
            return persona.language_code
        return I18N.locale

    def say_at_some_point(self, text, spot_profile, topic):
        save_mp3 = topic is not None and topic.value in config.save_tts_output_topics
        topic_str = "" if topic is None else topic.translate().replace(" ", "_")
        if spot_profile.immediate:
            self.say(text, topic=topic_str, save_mp3=save_mp3)
        else:
            self.prepare_to_say(text, topic=topic_str, save_mp3=save_mp3)

    def say(self, text, topic="", save_mp3=False, locale=None):
        self.voice.say(text=text, topic=topic, save_mp3=save_mp3, locale=self.get_locale(locale))

    def prepare_to_say(self, text, topic="", save_mp3=False, locale=None):
        self.voice.prepare_to_say(text=text, topic=topic, save_mp3=save_mp3, locale=self.get_locale(locale))

    def ready_to_prepare(self, cumulative_sleep_seconds, ms_remaining):
        return Muse.enable_preparation \
            and cumulative_sleep_seconds > Muse.preparation_starts_after_seconds_sleep \
            and not self.has_started_prep \
            and ms_remaining < int(Muse.preparation_starts_minutes_from_end * 60 * 1000)

    def prepare(self, spot_profile):
        self.has_started_prep = True
        self.set_topic(spot_profile)
        if self.ui_callbacks is not None:
            if self.ui_callbacks.update_next_up_callback is not None:
                self.ui_callbacks.update_next_up_callback(spot_profile.get_upcoming_track_title())
            if self.ui_callbacks.update_prior_track_callback is not None:
                self.ui_callbacks.update_prior_track_callback(spot_profile.get_previous_track_title())
            if self.ui_callbacks.update_spot_profile_topics_text is not None:
                self.ui_callbacks.update_spot_profile_topics_text(spot_profile.get_topic_text())
        if spot_profile.is_going_to_say_something():
            logger.debug(f"Preparing muse:\n{spot_profile}")
            if spot_profile.say_good_day:
                self.say_good_day()
                spot_profile.was_spoken = True
            if not spot_profile.skip_previous_track_remark:
                self.maybe_prep_dj_post(spot_profile)
            self.maybe_prep_dj_prior(spot_profile)
            self.memory.tracks_since_last_spoke = 0
        else:
            self.memory.tracks_since_last_spoke += 1
        spot_profile.set_preparation_time()
        spot_profile.is_prepared = True

    def cancel_preparation(self, spot_profile):
        logger.debug(f"Canceling muse prep:\n{spot_profile}")
        self.is_cancelled_prep = True
        if self.ui_callbacks is not None:
            if self.ui_callbacks.update_next_up_callback is not None:
                self.ui_callbacks.update_next_up_callback(spot_profile.get_upcoming_track_title())
            if self.ui_callbacks.update_prior_track_callback is not None:
                self.ui_callbacks.update_prior_track_callback(spot_profile.get_previous_track_title())
            if self.ui_callbacks.update_spot_profile_topics_text is not None:
                self.ui_callbacks.update_spot_profile_topics_text(spot_profile.get_topic_text())

    def maybe_dj(self, spot_profile):
        """If the DJ is prepared and will speak, wait for the speech queue to clear, then return immediately."""
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

    def check_schedules(self, get_upcoming_tracks_callback=None):
        self.check_for_shutdowns()
        if not self.args.muse:
            return
        now = datetime.datetime.now()
        active_schedule = SchedulesManager.get_active_schedule(now)
        if active_schedule is None:
            raise Exception("Failed to establish active schedule")
        if self._schedule != active_schedule or self._last_checked_schedules is None:
            if self._last_checked_schedules is None:
                logger.warning(f"Starting with DJ {active_schedule.voice} - until {active_schedule.next_end(now)}")
            else:
                logger.warning(f"Switching DJ to {active_schedule.voice} from {self._schedule.voice} - until {active_schedule.next_end(now)}")
            self.change_voice(active_schedule.voice, get_upcoming_tracks_callback)
        else:
            logger.info("No change in schedule")
        self._schedule = active_schedule
        self._last_checked_schedules = datetime.datetime.now()

    def change_voice(self, voice_name, get_upcoming_tracks_callback=None):
        """Switch to a new DJ persona by voice name."""
        try:
            # Find the persona with this voice name
            persona = self.memory.get_persona_manager().get_persona(voice_name)

            if persona:
                # Set the new persona
                self.memory.get_persona_manager().set_current_persona(persona.voice_name)
                self.voice = Voice(persona.voice_name, run_context=self._run_context)
                
                # Update UI with new persona
                if self.ui_callbacks and self.ui_callbacks.update_dj_persona_callback is not None:
                    self.ui_callbacks.update_dj_persona_callback(persona.name)

                try:
                    # Determine what type of introduction to use
                    intro_prompt, init_result = self._get_introduction_prompt(persona, get_upcoming_tracks_callback)

                    if intro_prompt:
                        context = init_result.context if init_result and init_result.context_provided else persona.get_context()
                        context = None # NOTE: not using context for now as it is being deprecated for some reason
                        intro_result = self.llm.ask(intro_prompt, context=context)
                        if intro_result and intro_result.response:
                            self.say(intro_result.response, locale=persona.language_code)
                            self.memory.get_persona_manager().update_context(intro_result)
                        else:
                            self.say(_("Hello, I'm {0}").format(persona.name), locale=persona.language_code)
                        persona.last_hello_time = time.time()
                except Exception as e:
                    logger.error(f"Failed to generate introduction: {e}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    self.say(_("Hello, I'm your DJ"), locale=I18N.locale)

                self.wiki_search = WikiOpenSearchAPI(language_code=persona.language_code)
            else:
                logger.warning(f"No persona found for voice {voice_name}, using default voice")
                self.voice = Voice(voice_name, run_context=self._run_context)
                # Update UI with fallback
                if self.ui_callbacks and self.ui_callbacks.update_dj_persona_callback is not None:
                    self.ui_callbacks.update_dj_persona_callback("")
                self.say(_("Hello, I'm your DJ"), locale=I18N.locale)
                
        except Exception as e:
            logger.error(f"Failed to change voice to {voice_name}: {e}")
            traceback.print_exc()
            # Ensure we at least have a working voice
            self.voice = Voice(voice_name, run_context=self._run_context)
            self.say(_("Hello"), locale=I18N.locale)

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
        self.prepare_to_say(_("The scheduled shutdown time has arrived. That's it for {0}.").format(now_general_word))
        tomorrow_schedule = SchedulesManager.get_active_schedule(tomorrow)
        if tomorrow_schedule is not None:
            if tomorrow_schedule.voice == self._schedule.voice:
                self.prepare_to_say(_("I'll be on again tomorrow."))
            else:
                self.prepare_to_say(_("Tomorrow you'll hear from {0}.").format(tomorrow_schedule.voice))
                next_weekday_for_this_voice = SchedulesManager.get_next_weekday_index_for_voice(self._schedule.voice, tomorrow)
                if next_weekday_for_this_voice is not None:
                    if next_weekday_for_this_voice == now.weekday():
                        self.prepare_to_say(_("The next time I'll be on is next week, at the same time."))
                    elif len(self._schedule.weekday_options) < 7:
                        self.prepare_to_say(_("I'll be on again this coming {0}.").format(I18N.day_of_the_week(next_weekday_for_this_voice)))
        self.voice.finish_speaking()
        self.get_current_persona().set_last_signoff_time()
        self._schedule = tomorrow_schedule

    def say_good_day(self):
        hour = SchedulesManager.get_hour()
        if hour < 5 or hour > 22:
            return
        logger.debug("Saying good day")
        if hour < 11:
            self.prepare_to_say(_("Good morning"))
        elif hour < 13:
            self.prepare_to_say(_("Good day"))
        elif hour < 17:
            self.prepare_to_say(_("Good afternoon"))
        else:
            self.prepare_to_say(_("Good evening"))

    def maybe_prep_dj_post(self, spot_profile):
        # TODO quality info for songs
        if spot_profile.speak_about_prior_track:
            self.speak_about_previous_track(spot_profile)
            spot_profile.was_spoken = True
        if spot_profile.speak_about_prior_group:
            self.speak_about_previous_group(spot_profile)
            spot_profile.was_spoken = True

    def speak_about_previous_track(self, spot_profile):
        # TODO have muse mention if the track has been split in the spot.
        # TODO make this better with new spot_profile methods to get more previous tracks
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
        spot_profile.mark_track_as_spoken(previous_track)
        self.say_at_some_point(dj_remark, spot_profile, None)

    def maybe_prep_dj_prior(self, spot_profile):
        # TODO quality info for songs
        if spot_profile.speak_about_upcoming_group:
            self.speak_about_upcoming_group(spot_profile)
            spot_profile.has_already_spoken = True
            spot_profile.was_spoken = True
        if spot_profile.speak_about_upcoming_track:
            self.speak_about_upcoming_track(spot_profile)
            spot_profile.has_already_spoken = True
            spot_profile.was_spoken = True
        # LLM failure backoff for topic discussion
        if spot_profile.talk_about_something:
            penalty = self.llm.get_llm_penalty()
            import random
            if random.random() < penalty:
                self.talk_about_something(spot_profile)
                spot_profile.was_spoken = True
            else:
                logger.info(f"Skipping talk_about_something due to LLM failure penalty (failures={self.llm.get_failure_count()}, penalty={penalty:.3f})")
        else:
            self.memory.tracks_since_last_topic += 1

    def speak_about_upcoming_track(self, spot_profile):
        # TODO have muse mention if the track has been split in the spot.
        # TODO make this better with new spot_profile methods to get more upcoming tracks
        track = spot_profile.track
        if spot_profile.previous_track is None:
            dj_remark = _("To start, we'll be playing: \"{0}\" from \"{1}\"").format(track.readable_title(), track.readable_album())
        else:
            dj_remark = _("Next up, we'll be playing: \"{0}\" from \"{1}\"").format(track.readable_title(), track.readable_album())
        if track.artist is not None and track.artist!= "":
            dj_remark += _(" by \"{0}\".").format(track.readable_artist())
        else:
            dj_remark += "."
        spot_profile.mark_track_as_spoken(track)
        if track._is_extended and random.random() < 0.8:
            dj_remark += " " + _("This one is a new track.")
            # extension_details = ExtensionManager.get_latest_extension_details()
            # if extension_details is not None:
            #     dj_remark += " " + _("I searched for: ") + extension_details.search_query
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
                
                # Sometimes add information about the group length for variety
                if random.random() < 0.7:  # 70% chance to mention group length
                    group_name = spot_profile.grouping_type.get_grouping_readable_name().lower()
                    length_remarks = [
                        _("This {0} has {1} tracks in total.").format(group_name, group_count),
                        _("There are {0} tracks in this {1}.").format(group_count, group_name),
                        _("We've got {0} tracks from this {1} coming up.").format(group_count, group_name),
                        _("This {0} contains {1} tracks.").format(group_name, group_count)
                    ]
                    dj_remark += " " + random.choice(length_remarks)
                
                self.say_at_some_point(dj_remark, spot_profile, None)

    def get_topic(self, previous_track, excluded_topics=[]):
        excluded_topics = list(excluded_topics)
        
        # Add randomness to the time thresholds
        weather_hours = random.uniform(20, 28)  # 20-28 hours for weather prioritization
        news_hours = random.uniform(72, 96)    # 3-4 days for news prioritization
        hackernews_hours = random.uniform(72, 96)  # 3-4 days for hackernews prioritization
        playlist_context_hours = random.uniform(0, 4) 
        min_repeat_hours = random.uniform(12, 16)   # 12-16 hours minimum repeat
        
        if Prompter.over_n_hours_since_last(Topic.WEATHER, n_hours=weather_hours) and not self.memory.is_recent_topics([Topic.NEWS, Topic.HACKERNEWS], n=3):
            topic = Topic.WEATHER
        elif Prompter.over_n_hours_since_last(Topic.NEWS, n_hours=news_hours) and not self.memory.is_recent_topics([Topic.WEATHER, Topic.HACKERNEWS], n=3):
            topic = Topic.NEWS
        elif Prompter.over_n_hours_since_last(Topic.HACKERNEWS, n_hours=hackernews_hours) and not self.memory.is_recent_topics([Topic.WEATHER, Topic.NEWS], n=3):
            topic = Topic.HACKERNEWS
        elif (Prompter.over_n_hours_since_last(Topic.PLAYLIST_CONTEXT, n_hours=playlist_context_hours) 
                and not self.memory.is_recent_topics([Topic.WEATHER, Topic.NEWS, Topic.HACKERNEWS], n=1)
                and not self.memory.is_recent_topics([Topic.PLAYLIST_CONTEXT], n=5)):
            topic = Topic.PLAYLIST_CONTEXT
        else:
            # Add randomness to topic selection by occasionally skipping the oldest topic
            if random.random() < 0.3:  # 30% chance to not pick the oldest topic
                excluded_topics.append(Prompter.get_oldest_topic(excluded_topics=excluded_topics))
            topic = Prompter.get_oldest_topic(excluded_topics=excluded_topics)

        if topic not in excluded_topics:
            if topic in [Topic.HACKERNEWS, Topic.NEWS] and Prompter.under_n_hours_since_last(topic, n_hours=min_repeat_hours):
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
        logger.info(f"Talking about topic: {topic.value}")

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
        elif topic == Topic.PLAYLIST_CONTEXT:
            func = self.talk_about_playlist_context
        elif topic == Topic.RANDOM_WIKI_ARTICLE:
            func = self.talk_about_random_wiki_article
        elif topic == Topic.FUNNY_STORY:
            func = self.share_a_funny_story
        elif topic == Topic.LANGUAGE_LEARNING:
            func = self.teach_language
        else:
            logger.warning(f"Unhandled topic: {topic}")
            return

        self._wrap_function(spot_profile, topic, func, args, kwargs)
        
        # Update the last topic that was discussed
        self.memory.update_last_topic(topic)

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
        logger.info(f"Playing tongue twister from {config.tongue_twisters_dir}")
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
        prompt = prompt.format(TRACK_DETAILS=track.get_track_details())
        track_context = self.generate_text(prompt)
        self.say_at_some_point(track_context, spot_profile, None)

    def talk_about_playlist_context(self, spot_profile):
        # Counts are higher for upcoming tracks to bias the response towards what to expect next.
        previous_tracks = spot_profile.get_previous_tracks(count=random.randint(1, 5))
        upcoming_tracks = spot_profile.get_upcoming_tracks(count=random.randint(3, 8))
        prompt = self.get_prompt(Topic.PLAYLIST_CONTEXT)
        already_mentioned = _(' [already mentioned]')
        prompt = prompt.format(PREVIOUS_TRACKS="\n".join([f" - {t.get_track_details()}{already_mentioned if was_spoken else ''}" for t, was_spoken in previous_tracks]),
                               UPCOMING_TRACKS="\n".join([f" - {t.get_track_details()}{already_mentioned if was_spoken else ''}" for t, was_spoken in upcoming_tracks]))
        playlist_context = self.generate_text(prompt)
        self.say_at_some_point(playlist_context, spot_profile, Topic.PLAYLIST_CONTEXT)

    def talk_about_random_wiki_article(self, spot_profile):
        article_blacklisted = True
        blacklisted_words_found = set()
        count = 0
        while article_blacklisted:
            article = self.wiki_search.random_wiki()
            if article is None or not article.is_valid():
                raise Exception("No valid wiki article found")
            article_text = str(article)[:2000]
            blacklist_words = list(Blacklist.find_blacklisted_items(article_text).keys())
            blacklisted_words_found.update(blacklist_words)
            article_blacklisted = len(blacklist_words) > 0
            if count > 10:
                raise Exception(f"No valid wiki article found after 10 tries. Blacklisted words: {blacklisted_words_found}")
            count += 1
        prompt = self.get_prompt(Topic.RANDOM_WIKI_ARTICLE)
        prompt = prompt.format(ARTICLE=str(article)[:2000])
        summary = self.generate_text(prompt)
        self.say_at_some_point(summary, spot_profile, Topic.RANDOM_WIKI_ARTICLE)

    def share_a_funny_story(self, spot_profile):
        funny_story = self.generate_text(self.get_prompt(Topic.FUNNY_STORY))
        self.say_at_some_point(funny_story, spot_profile, Topic.FUNNY_STORY)

    def teach_language(self, spot_profile):
        prompt = self.get_prompt(Topic.LANGUAGE_LEARNING)
        prompt = prompt.format(
            LANGUAGE=config.muse_language_learning_language,
            LEVEL=config.muse_language_learning_language_level.strip() if config.muse_language_learning_language_level and config.muse_language_learning_language_level.strip() else "basic"
        )
        language_response = self.generate_text(prompt)
        self.say_at_some_point(language_response, spot_profile, Topic.LANGUAGE_LEARNING)

    def start_extensions_thread(self, initial_sleep=True, overwrite_cache=False):
        self.get_library_data().start_extensions_thread(initial_sleep=initial_sleep, overwrite_cache=overwrite_cache, voice=self.voice)

    def should_use_two_call_approach(self) -> bool:
        """Determine if we should use the two-call translation approach for added variety."""
        return random.random() < 0.05  # 5% chance to use two-call approach - it is very slow

    def get_prompt(self, topic):
        prompt = self.prompter.get_prompt_update_history(topic)
        if not self.args.use_system_language_for_all_topics:
            return prompt
        
        # Get the current persona's language code
        persona = self.get_current_persona()
        language_code = persona.language_code if persona else Utils.get_default_user_language()
        language = Utils.get_english_language_name(language_code) if persona else Muse.SYSTEM_LANGUAGE_NAME_IN_ENGLISH
        
        # Special case for language learning
        if topic == Topic.LANGUAGE_LEARNING:
            # Don't replace the whole prompt, it would be trying to teach the same language the prompt is already in.
            if persona and language == config.muse_language_learning_language:
                return prompt
            language_code = Utils.get_default_user_language()
        
        # If language is English or not supported, use English
        if language_code == "en" or language_code not in SUPPORTED_LANGUAGE_CODES:
            logger.warning(f"No translation available for language {language_code} topic {topic}, using English")
            return prompt
        
        try:
            # Use two-call approach occasionally for added variety
            if self.should_use_two_call_approach():
                translation_prompt = self.prompter.get_translation_prompt(language_code, language, prompt)
                prompt = self.generate_text(translation_prompt, json_key="prompt")
            else:
                prompt = self.prompter.get_prompt_with_language(topic, language_code)
        except Exception as e:
            logger.info(f"Failed to translate prompt for topic {topic} into language {language_code} with error: {e}")
        return prompt

    def generate_text(self, prompt, json_key=None, include_time_context=True):
        """Generate text using the current DJ persona's context."""
        # Get the current persona's context and system prompt
        context, system_prompt = self.memory.get_persona_manager().get_context_and_system_prompt()
        language_code = self.get_current_persona().language_code
        
        # If we have no persona/context, use language-specific default prompt
        if not system_prompt:
            logger.warning("No system prompt available, using default prompt")
            language_code = Utils.get_default_user_language()
            system_prompt = self.prompter.get_prompt("default_system_prompt", language_code)
        
        if include_time_context:
            # Get current time information
            now = datetime.datetime.now()
            
            # Add time context to the prompt
            time_context = self.prompter.get_prompt("time_context", language_code).format(
                time=now.strftime("%I:%M %p"),
                day=I18N.day_of_the_week(now.weekday()),
                date=now.strftime("%B %d, %Y")
            )
            prompt = prompt + "\n" + time_context
        
        prompt_text_to_test = prompt
        variant_part_marker = "----"
        if variant_part_marker in prompt_text_to_test:
            prompt_text_to_test = prompt_text_to_test[prompt_text_to_test.index(variant_part_marker):]
            prompt_text_to_test = prompt_text_to_test[prompt_text_to_test.index("\n") + 1:]
        blacklisted_items_in_prompt = list(Blacklist.find_blacklisted_items(prompt_text_to_test).keys())
        
        # Use the context and system prompt in the LLM call
        # NOTE excluding context for now because it's being deprecated for some reason.
        result = self.llm.ask(prompt, json_key=json_key, context=None, system_prompt=system_prompt)
        text = result.response if result else ""
        
        # Update context with the new context from the response
        self.memory.get_persona_manager().update_context(result)
        
        generations = []
        all_blacklist_items = set()
        blacklist_items = list(Blacklist.find_blacklisted_items(text).keys())
        # Filter out excluded items (items already in prompt)
        blacklist_items = [item for item in blacklist_items if item not in blacklisted_items_in_prompt]
        attempts = 0
        while len(blacklist_items) > 0:
            all_blacklist_items.update(set(blacklist_items))
            blacklist_items_str = ", ".join(sorted([str(i) for i in all_blacklist_items]))
            logger.info("Hit blacklisted items: " + blacklist_items_str)
            logger.info("Text: " + text)
            # NOTE excluding context for now because it's being deprecated for some reason.
            result = self.llm.ask(prompt, json_key=json_key, context=None, system_prompt=system_prompt)
            text = result.response if result else ""
            if text.strip() == "":
                raise LLMResponseException("No response text was generated!")
            generations.append(text)
            blacklist_items = list(Blacklist.find_blacklisted_items(text).keys())
            # Filter out excluded items (items already in prompt)
            blacklist_items = [item for item in blacklist_items if item not in blacklisted_items_in_prompt]
            attempts += 1
            if attempts > 2:
                blacklist_items_str = ", ".join(sorted([str(i) for i in all_blacklist_items]))
                texts_str = "\n".join(generations)
                raise BlacklistException(
                    f"Failed to generate text - blacklist items found: {blacklist_items_str}\n{texts_str}",
                    filtered=all_blacklist_items
                )
        return text

    def _wrap_function(self, spot_profile, topic, func, _args=[], _kwargs={}):
        try:
            result = func(*_args, **_kwargs)
            return result
        except WebConnectionException as e:
            logger.error(e)
            self.say_at_some_point(_("We're having some technical difficulties in accessing our source for {0}. We'll try again later").format(topic),
                                   spot_profile, None)
        except LLMResponseException as e:
            logger.error(e)
            self.say_at_some_point(_("It seems our writer for {0} is unexpectedly away at the moment. Did we forget to pay his salary again?").format(topic),
                                   spot_profile, None)
        except BlacklistException as e:
            logger.error(e)
            self.say_at_some_point(_("We've found problems with all of our {0} ideas. Please try again later.").format(topic),
                                   spot_profile, None)
        except Exception as e:
            logger.error(e)
            traceback.print_exc()
            self.say_at_some_point(_("Something went wrong. We'll try to fix it soon."), spot_profile, None)

    def _get_introduction_prompt(self, persona: Optional[DJPersona],
                                 get_upcoming_tracks_callback: Optional[Callable[[int], List[MediaTrack]]] = None
                                ) -> tuple[Optional[str], Optional[LLMResult]]:
        """Determine what type of introduction to use based on timing of last interactions, initialize the persona, and return the prompt.
        
        Args:
            persona: The DJ persona to use for the introduction
            get_upcoming_tracks_callback: Optional callback to get upcoming tracks
            
        Returns:
            tuple[Optional[str], Optional[LLMResult]]: A tuple containing:
                - The formatted introduction prompt (or None if no introduction needed)
                - The LLM result from persona initialization
        """
        if not persona:
            return None, None

        # NOTE the below needs to happen before "persona_init" prompt because
        # `persona.update_context` will set the last signoff time
        intro_type = self._determine_intro_type(time.time(), persona)
        if intro_type == IntroType.NONE:
            return None, None

        # Get current time information
        now = datetime.datetime.now()
        day = I18N.day_of_the_week(now.weekday())
        date = now.strftime("%B %d, %Y")

        # Get language information
        language_code = persona.language_code
        language_name = persona.language
        
        # Get the persona initialization prompt and format it
        persona_init_prompt = self.prompter.get_persona_initialization_prompt(language_code)
        persona_init_prompt = persona_init_prompt.format(
            name=persona.name,
            sex=persona.get_s(),
            tone=persona.tone,
            characteristics=", ".join(persona.characteristics),
            system_prompt=persona.system_prompt,
            time=now.strftime("%I:%M %p"),
            day=day,
            date=date,
            language_code=language_code,
            language_name=language_name,
        )
        
        # Make an initial call to seed the context, using the old context
        result = self.llm.ask(persona_init_prompt, context=None)
        if result:
            self.memory.get_persona_manager().update_context(result)
        else:
            logger.warning(f"Result was None for {persona.name} initial persona prompt, possibly due to user skip.")
            return None, None

        # Get starting tracks if callback is provided
        starting_tracks_str = ""
        if get_upcoming_tracks_callback:
            try:
                # Get a random number of upcoming tracks (between 3 and 8)
                upcoming_tracks = get_upcoming_tracks_callback(random.randint(3, 8))
                if upcoming_tracks:
                    upcoming_tracks_str = "\n".join([f" - {t.get_track_details()}" for t in upcoming_tracks])
                logger.info(f"Starting intro with tracks:\n{upcoming_tracks_str}")
                starting_tracks_str = _("Starting tracks:") + "\n" + upcoming_tracks_str
            except Exception as e:
                logger.info(f"Error getting upcoming tracks: {e}")

        # Get the appropriate introduction prompt
        template_name = intro_type.get_template_name()
        if not template_name: # Should never happen
            raise Exception(f"Unhandled intro type: {intro_type}")
        intro_prompt = self.prompter.get_prompt(template_name, language_code)
        format_args = {
            "name": persona.name,
            "time": now.strftime("%I:%M %p"),
            "day": day,
            "date": date,
            "language_code": language_code,
            "language_name": language_name,
            "starting_tracks": starting_tracks_str,
        }
        if intro_type == IntroType.REINTRO:
            last_tuned_in_str = persona.get_last_tuned_in_str()
            format_args["last_tuned_in_str"] = last_tuned_in_str
        intro_prompt = intro_prompt.format(**format_args)
        return intro_prompt, result

    def _determine_intro_type(self, now_time: float, persona: DJPersona) -> IntroType:
        last_hello = persona.last_hello_time or 0
        last_signoff = persona.last_signoff_time or 0

        # If neither hello nor signoff has been said recently, or it's been a long time
        if last_hello == 0 or last_signoff == 0 or (now_time - last_hello > 6 * 3600 and now_time - last_signoff > 6 * 3600):
            logger.debug("intro case 1: last_hello: {0}, last_signoff: {1}, now_time: {2}".format(last_hello, last_signoff, now_time))
            return IntroType.INTRO  
        
        # Check if the time difference spans across sleeping hours
        last_signoff_dt = datetime.datetime.fromtimestamp(last_signoff)
        now_dt = datetime.datetime.fromtimestamp(now_time)
        
        # If the time difference is less than 12 hours but greater than 4 hours and 
        # spans across sleeping hours (11 PM to 6 AM), treat it as a long absence
        if ((4 * 3600) < (now_time - last_signoff) < (12 * 3600) and 
                ((last_signoff_dt.hour >= 23 or last_signoff_dt.hour < 6) and
                 (now_dt.hour > 4 and now_dt.hour < 10))):
            logger.debug("intro case 2: last_hello: {0}, last_signoff: {1}, now_time: {2}".format(last_hello, last_signoff, now_time))
            return IntroType.INTRO
            
        # If hello hasn't been said recently but signoff was recent (1-6 hours ago)
        elif now_time - last_hello > 2 * 3600 and 1 * 3600 < now_time - last_signoff <= 6 * 3600:
            logger.debug("reintro: last_hello: {0}, last_signoff: {1}, now_time: {2}".format(last_hello, last_signoff, now_time))
            return IntroType.REINTRO
        else:
            # If both hello and signoff were recent, don't say anything
            logger.debug("no intro: last_hello: {0}, last_signoff: {1}, now_time: {2}".format(last_hello, last_signoff, now_time))
            return IntroType.NONE


