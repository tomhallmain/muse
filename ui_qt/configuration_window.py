"""
Configuration settings window (PySide6).
Port of ui/configuration_window.py; logic preserved, UI uses Qt.
"""

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QWidget,
    QFrame,
    QGroupBox,
    QListWidget,
    QScrollArea,
    QFileDialog,
)
from PySide6.QtCore import Qt

from lib.multi_display_qt import SmartWindow
from muse.playlist import (
    GROUP_MAX_MINUTES_KEY,
    GROUP_MAX_TRACKS_KEY,
    TRACK_EXCLUSIONS_KEY,
    DEFAULT_TRACK_EXCLUSIONS,
)
from muse.track_affinity import AFFINITY_OFF, AFFINITY_ON
from ui_qt.app_style import AppStyle
from ui_qt.auth.password_utils import require_password
from utils.app_info_cache import app_info_cache
from utils.app_paths import IS_BUILD
from utils.config import config
from utils.globals import Globals, ProtectedActions, Topic
from utils.translations import I18N, SUPPORTED_LANGUAGE_CODES

_ = I18N._


class ConfigurationWindow(SmartWindow):
    """Configuration settings dialog with tabbed interface."""

    top_level = None

    def __init__(self, master, app_actions):
        super().__init__(
            persistent_parent=master,
            position_parent=master,
            title=_("Configuration Settings"),
            geometry="1000x800",
            offset_x=50,
            offset_y=50,
        )
        ConfigurationWindow.top_level = self
        self.master = master
        self.app_actions = app_actions

        # key -> (widget, "entry" | "checkbox" | "combo" | "combo_value") for save
        self.config_vars = {}
        # key -> (QListWidget, "list" | "trust") for list- and dict-shaped settings
        self._list_editors = {}
        # (key, widget, "bool" | "int" | "float") for the nested muse_config dict
        self._muse_inputs = []
        self._tts_topic_checks = {}

        self.setStyleSheet(AppStyle.get_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.notebook = QTabWidget(self)
        self.general_tab = QWidget(self)
        self.audio_tab = QWidget(self)
        self.api_tab = QWidget(self)
        self.tts_tab = QWidget(self)
        self.playlist_options_tab = QWidget(self)

        self.notebook.addTab(self.general_tab, _("General"))
        self.notebook.addTab(self.audio_tab, _("Audio"))
        self.notebook.addTab(self.api_tab, _("API Keys"))
        self.notebook.addTab(self.tts_tab, _("TTS Settings"))
        self.notebook.addTab(self.playlist_options_tab, _("Playlist Options"))

        self.create_general_tab()
        self.create_audio_tab()
        self.create_api_tab()
        self.create_tts_tab()
        self.create_playlist_options_tab()

        layout.addWidget(self.notebook)

        self.save_button = QPushButton(_("Save Configuration"), self)
        self.save_button.clicked.connect(self.save_config)
        layout.addWidget(self.save_button)

        self.show()

    def _locale_choices(self):
        """(code, label) pairs. The code is what gets stored."""
        names = {
            "en": _("English"),
            "de": _("German"),
            "es": _("Spanish"),
            "fr": _("French"),
            "it": _("Italian"),
            "pt": _("Portuguese"),
            "ru": _("Russian"),
        }
        current = config.get_config_value("locale") or I18N.locale or "en"
        codes = list(SUPPORTED_LANGUAGE_CODES)
        if current not in codes:
            codes.append(current)
        choices = []
        for code in codes:
            name = names.get(code)
            choices.append((code, f"{name} ({code})" if name else code))
        return choices

    def create_general_tab(self):
        scroll, content, outer = self._begin_scroll_tab(self.general_tab)

        appearance = QGroupBox(_("Appearance"), content)
        layout = QGridLayout(appearance)
        self.add_config_value_combo(
            appearance, layout, "locale", _("Interface Language"), 0, self._locale_choices(),
        )
        hint = QLabel(
            _("Language of menus and buttons. Restart after saving so windows "
              "that are already open pick up the new language."),
            appearance,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint, 1, 0, 1, 2)
        self.add_config_entry(appearance, layout, "foreground_color", _("Foreground Color"), 2)
        self.add_config_entry(appearance, layout, "background_color", _("Background Color"), 3)
        self.add_config_checkbox(appearance, layout, "debug", _("Write Debug Logs"), 4)
        self.add_config_checkbox(
            appearance, layout, "auto_fix_vlc_plugin_cache",
            _("Repair the VLC Plugin Cache When It Is Out of Date"), 5,
        )
        self.add_config_checkbox(appearance, layout, "enable_dynamic_volume", _("Enable Dynamic Volume"), 6)
        # Extension checkboxes live in the Extensions window's Extension Config.
        self.add_config_checkbox(
            appearance, layout, "enable_long_track_splitting", _("Enable Long Track Splitting"), 7,
        )
        self.add_config_entry(
            appearance, layout, "long_track_splitting_time_cutoff_minutes",
            _("Long Track Cutoff (minutes)"), 8,
        )
        outer.addWidget(appearance)
        outer.addWidget(self._build_directories_group(content))
        outer.addWidget(self._build_library_files_group(content))
        outer.addWidget(self._build_muse_group(content))
        outer.addWidget(self._build_language_learning_group(content))
        outer.addStretch()
        scroll.setWidget(content)

    def _build_directories_group(self, parent):
        group = QGroupBox(_("Library Directories"), parent)
        layout = QVBoxLayout(group)
        desc = QLabel(_("Folders scanned into the music library."), group)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addWidget(self.add_string_list(
            group, "directories",
            [d for d in (config.directories or []) if d],
            _("Directory path"),
            browse="dir",
        ))
        return group

    def _build_library_files_group(self, parent):
        group = QGroupBox(_("Library Data Files"), parent)
        layout = QGridLayout(group)
        self.add_config_dirpath_entry(group, layout, "prompts_directory", _("Prompts Directory"), 0)
        self.add_config_dirpath_entry(
            group, layout, "tongue_twisters_dir", _("Tongue Twisters Directory"), 1,
        )
        self.add_config_filepath_entry(
            group, layout, "artists_file", _("Artists File"), 2, _("JSON files") + " (*.json)",
        )
        self.add_config_filepath_entry(
            group, layout, "forms_file", _("Forms File"), 3, _("JSON files") + " (*.json)",
        )
        self.add_config_filepath_entry(
            group, layout, "genres_file", _("Genres File"), 4, _("JSON files") + " (*.json)",
        )
        self.add_config_filepath_entry(
            group, layout, "instruments_file", _("Instruments File"), 5, _("JSON files") + " (*.json)",
        )
        return group

    def _build_muse_group(self, parent):
        """DJ speaking chances. Stored together as the muse_config object."""
        group = QGroupBox(_("Muse"), parent)
        layout = QGridLayout(group)
        desc = QLabel(
            _("When the DJ speaks, and how often. Chances are fractions between 0 and 1."),
            group,
        )
        desc.setWordWrap(True)
        layout.addWidget(desc, 0, 0, 1, 2)

        muse = config.muse_config or {}
        specs = [
            (Globals.ConfigKeys.ENABLE_PREPARATION,
             _("Prepare the next spot before the track ends"), "bool"),
            (Globals.ConfigKeys.PREPARATION_STARTS_MINUTES_FROM_END,
             _("Start preparation this many minutes before the end"), "int"),
            (Globals.ConfigKeys.PREPARATION_STARTS_AFTER_SECONDS_SLEEP,
             _("Or after this many seconds, whichever is sooner"), "int"),
            (Globals.ConfigKeys.CHANCE_SPEAK_BEFORE_TRACK, _("Chance of speaking before a track"), "float"),
            (Globals.ConfigKeys.CHANCE_SPEAK_AFTER_TRACK, _("Chance of speaking after a track"), "float"),
            (Globals.ConfigKeys.TOPIC_DISCUSSION_CHANCE_FACTOR, _("Topic discussion chance factor"), "float"),
            (Globals.ConfigKeys.MIN_SECONDS_BETWEEN_SPOTS, _("Minimum seconds between spots"), "int"),
        ]
        for row, (key, label, kind) in enumerate(specs, start=1):
            value = muse.get(key, "")
            if kind == "bool":
                widget = QCheckBox(label, group)
                widget.setChecked(bool(value) if value != "" else True)
                layout.addWidget(widget, row, 0, 1, 2)
            else:
                layout.addWidget(QLabel(label, group), row, 0)
                widget = QLineEdit(group)
                widget.setText("" if value is None else str(value))
                layout.addWidget(widget, row, 1)
            self._muse_inputs.append((key, widget, kind))

        refresh = QCheckBox(_("Refresh persona context when the persona changes"), group)
        refresh.setChecked(bool(config.get_config_value("dj_persona_refresh_context")))
        layout.addWidget(refresh, len(specs) + 1, 0, 1, 2)
        self.config_vars["dj_persona_refresh_context"] = (refresh, "checkbox")
        return group

    def _build_language_learning_group(self, parent):
        """Languages the listener is currently learning (with a level each).

        A persona can only run the language-learning topic for languages in this
        list that its own `can_teach_languages` allows (see personas window);
        a persona allowed to teach more than one rotates between them.
        """
        group = QGroupBox(_("Language Learning"), parent)
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(6)

        desc = QLabel(
            _("Languages the listener is currently learning. Add more than one if "
              "you're learning several at once -- each persona teaches only the "
              "ones its \"Can Teach Languages\" setting allows."),
            group,
        )
        desc.setWordWrap(True)
        group_layout.addWidget(desc)

        self._language_learning_list = QListWidget(group)
        for entry in config.muse_language_learning_languages:
            code = entry.get("language_code", "")
            level = entry.get("level", "")
            self._language_learning_list.addItem(f"{code}: {level}")
        group_layout.addWidget(self._language_learning_list)

        add_row = QWidget(group)
        add_layout = QHBoxLayout(add_row)
        add_layout.setContentsMargins(0, 0, 0, 0)
        self._language_learning_code_combo = QComboBox(add_row)
        self._language_learning_code_combo.addItems(SUPPORTED_LANGUAGE_CODES)
        add_layout.addWidget(self._language_learning_code_combo)
        self._language_learning_level_entry = QLineEdit(add_row)
        self._language_learning_level_entry.setPlaceholderText(_("Level (e.g. beginner, intermediate)"))
        add_layout.addWidget(self._language_learning_level_entry)
        add_btn = QPushButton(_("Add"), add_row)
        add_btn.clicked.connect(self._add_language_learning_entry)
        add_layout.addWidget(add_btn)
        remove_btn = QPushButton(_("Remove Selected"), add_row)
        remove_btn.clicked.connect(self._remove_language_learning_entry)
        add_layout.addWidget(remove_btn)
        group_layout.addWidget(add_row)

        return group

    def _add_language_learning_entry(self):
        code = self._language_learning_code_combo.currentText()
        level = self._language_learning_level_entry.text().strip() or "intermediate"
        existing_codes = [
            self._language_learning_list.item(i).text().split(":", 1)[0]
            for i in range(self._language_learning_list.count())
        ]
        if code in existing_codes:
            return
        self._language_learning_list.addItem(f"{code}: {level}")
        self._language_learning_level_entry.clear()

    def _remove_language_learning_entry(self):
        for item in self._language_learning_list.selectedItems():
            self._language_learning_list.takeItem(self._language_learning_list.row(item))

    def create_audio_tab(self):
        scroll, content, outer = self._begin_scroll_tab(self.audio_tab)

        playback = QGroupBox(_("Playback"), content)
        layout = QGridLayout(playback)
        self.add_config_checkbox(
            playback, layout, "play_videos_in_separate_window", _("Play Videos in Separate Window"), 0
        )
        self.add_config_checkbox(
            playback, layout, "show_videos_in_main_window", _("Play Videos in the Main Window"), 1,
        )
        self.add_config_checkbox(
            playback, layout, "spinning_record_videos",
            _("Show a Spinning Record Video When a Track Has No Album Art"), 2,
        )
        self.add_config_checkbox(
            playback, layout, "main_artist_prefers_last_segment",
            _("Main Artist Shuffle: Use the Last Name in a Combined Credit"), 3,
        )
        self.add_config_checkbox(
            playback, layout, "auto_fix_album_artwork",
            _("Copy an Album's Best Artwork to Its Other Tracks"), 4,
        )
        self.add_config_value_combo(
            playback, layout, "affinity_preference", _("Upcoming Track Ordering"), 5,
            [
                (AFFINITY_ON, _("On")),
                (AFFINITY_OFF, _("Off")),
            ],
        )
        self.add_config_entry(
            playback, layout, "playlist_recently_played_check_count", _("Recently Played Check Count"), 6
        )
        self.add_config_entry(
            playback, layout, "play_count_threshold_ratio",
            _("Fraction of a Track That Counts as a Play"), 7,
        )
        self.add_config_entry(
            playback, layout, "play_count_threshold_cap_seconds",
            _("Seconds That Always Count as a Play (0 to disable)"), 8,
        )
        outer.addWidget(playback)

        search = QGroupBox(_("Search"), content)
        search_layout = QGridLayout(search)
        self.add_config_entry(search, search_layout, "max_search_results", _("Max Search Results"), 0)
        self.add_config_entry(search, search_layout, "max_recent_searches", _("Max Recent Searches"), 1)
        self.add_config_checkbox(
            search, search_layout, "search_enable_embedding_ranking",
            _("Rank Search Results with Text Embeddings"), 2,
        )
        self.add_config_checkbox(
            search, search_layout, "search_enable_semantic_recall",
            _("Include Tracks Whose Text Is Close to the Query"), 3,
        )
        search_layout.addWidget(QLabel(_("Fields Indexed for Semantic Search"), search), 4, 0)
        search_layout.addWidget(self.add_string_list(
            search, "search_semantic_fields", config.search_semantic_fields,
            _("Field name, such as title"),
        ), 4, 1)
        self.add_config_entry(search, search_layout, "search_semantic_top_k", _("Semantic Candidates per Query"), 5)
        self.add_config_entry(
            search, search_layout, "search_semantic_relative_floor",
            _("Keep Candidates Within This of the Best Score"), 6,
        )
        self.add_config_entry(
            search, search_layout, "search_semantic_min_score", _("Minimum Semantic Score"), 7,
        )
        outer.addWidget(search)
        outer.addWidget(self._build_radio_group(content))
        outer.addStretch()
        scroll.setWidget(content)

    def _build_radio_group(self, parent):
        group = QGroupBox(_("Internet Radio"), parent)
        layout = QGridLayout(group)
        self.add_config_checkbox(
            group, layout, "radio_watchlist_enabled", _("Watch Saved Stations for Matching Tracks"), 0,
        )
        self.add_config_entry(
            group, layout, "radio_watchlist_cooldown_minutes", _("Minutes Between Alerts for One Station"), 1,
        )
        self.add_config_entry(
            group, layout, "radio_watchlist_max_stations", _("Maximum Watched Stations"), 2,
        )
        self.add_config_entry(
            group, layout, "radio_heard_min_seconds", _("Seconds Before a Stream Title Counts as Heard"), 3,
        )
        self.add_config_entry(
            group, layout, "radio_novelty_warmup_minutes", _("Minutes Before Suggesting Unfamiliar Tracks"), 4,
        )
        self.add_config_entry(
            group, layout, "radio_novelty_suggestion_cooldown_minutes",
            _("Minutes Between Discovery Suggestions"), 5,
        )
        self.add_config_entry(
            group, layout, "radio_novelty_seen_titles_per_station",
            _("Remember This Many Titles per Station"), 6,
        )
        layout.addWidget(QLabel(_("Titles That Are Not Tracks"), group), 7, 0)
        layout.addWidget(self.add_string_list(
            group, "radio_novelty_non_track_patterns",
            config.radio_novelty_non_track_patterns, _("Pattern, such as jingle"),
        ), 7, 1)
        layout.addWidget(QLabel(_("Tags Treated as Classical"), group), 8, 0)
        layout.addWidget(self.add_string_list(
            group, "radio_novelty_classical_tags",
            config.radio_novelty_classical_tags, _("Tag, such as classical"),
        ), 8, 1)
        return group

    def create_api_tab(self):
        scroll, content, outer = self._begin_scroll_tab(self.api_tab)

        weather = QGroupBox(_("Weather and News"), content)
        layout = QGridLayout(weather)
        self.add_config_entry(weather, layout, "open_weather_api_key", _("OpenWeather API Key"), 0)
        self.add_config_entry(weather, layout, "open_weather_city", _("OpenWeather City"), 1)
        self.add_config_entry(weather, layout, "news_api_key", _("News API Key"), 2)
        self.add_config_entry(weather, layout, "lastfm_api_key", _("Last.fm API Key"), 3)
        self.add_config_entry(weather, layout, "library_extender_key", _("Library Extender Key"), 4)
        layout.addWidget(QLabel(_("News Source Trustworthiness"), weather), 5, 0)
        trust_lines = [
            f"{name}: {score}"
            for name, score in (config.news_api_source_trustworthiness or {}).items()
        ]
        layout.addWidget(self.add_string_list(
            weather, "news_api_source_trustworthiness", trust_lines,
            _("source-id: 0.5"), kind="trust",
        ), 5, 1)
        outer.addWidget(weather)

        reddit = QGroupBox(_("Reddit"), content)
        reddit_layout = QGridLayout(reddit)
        desc = QLabel(
            _("Leave the id and secret blank to use the public listing. "
              "The subreddit list is the only source that gets read."),
            reddit,
        )
        desc.setWordWrap(True)
        reddit_layout.addWidget(desc, 0, 0, 1, 2)
        self.add_config_entry(reddit, reddit_layout, "reddit_client_id", _("Client Id"), 1)
        self.add_config_entry(reddit, reddit_layout, "reddit_client_secret", _("Client Secret"), 2)
        self._secret_entry("reddit_client_secret")
        self.add_config_entry(reddit, reddit_layout, "reddit_min_score", _("Minimum Score"), 3)
        self.add_config_entry(reddit, reddit_layout, "reddit_max_age_hours", _("Maximum Age (hours)"), 4)
        reddit_layout.addWidget(QLabel(_("Subreddits"), reddit), 5, 0)
        reddit_layout.addWidget(self.add_string_list(
            reddit, "reddit_subreddits", config.reddit_subreddits, _("Subreddit name"),
        ), 5, 1)
        outer.addWidget(reddit)

        bluesky = QGroupBox(_("Bluesky"), content)
        bluesky_layout = QGridLayout(bluesky)
        bluesky_desc = QLabel(
            _("Leave the handle and app password blank to read the public AppView. "
              "The feed list is the only source that gets read."),
            bluesky,
        )
        bluesky_desc.setWordWrap(True)
        bluesky_layout.addWidget(bluesky_desc, 0, 0, 1, 2)
        self.add_config_entry(bluesky, bluesky_layout, "bluesky_handle", _("Handle"), 1)
        self.add_config_entry(bluesky, bluesky_layout, "bluesky_app_password", _("App Password"), 2)
        self._secret_entry("bluesky_app_password")
        self.add_config_entry(bluesky, bluesky_layout, "bluesky_min_score", _("Minimum Score"), 3)
        self.add_config_entry(bluesky, bluesky_layout, "bluesky_max_age_hours", _("Maximum Age (hours)"), 4)
        bluesky_layout.addWidget(QLabel(_("Feed URIs"), bluesky), 5, 0)
        bluesky_layout.addWidget(self.add_string_list(
            bluesky, "bluesky_feeds", config.bluesky_feeds, _("at:// feed URI"),
        ), 5, 1)
        bluesky_layout.addWidget(QLabel(_("Languages"), bluesky), 6, 0)
        bluesky_layout.addWidget(self.add_string_list(
            bluesky, "bluesky_languages", config.bluesky_languages, _("Language code, such as en"),
        ), 6, 1)
        outer.addWidget(bluesky)

        mastodon = QGroupBox(_("Mastodon"), content)
        mastodon_layout = QGridLayout(mastodon)
        self.add_config_entry(mastodon, mastodon_layout, "mastodon_instance", _("Instance"), 0)
        self.add_config_entry(mastodon, mastodon_layout, "mastodon_min_score", _("Minimum Score"), 1)
        self.add_config_entry(mastodon, mastodon_layout, "mastodon_max_age_hours", _("Maximum Age (hours)"), 2)
        mastodon_layout.addWidget(QLabel(_("Languages"), mastodon), 3, 0)
        mastodon_layout.addWidget(self.add_string_list(
            mastodon, "mastodon_languages", config.mastodon_languages, _("Language code, such as en"),
        ), 3, 1)
        outer.addWidget(mastodon)

        social = QGroupBox(_("All Social Sources"), content)
        social_layout = QGridLayout(social)
        social_desc = QLabel(
            _("A topic is dropped when filtering removes more than this share of its posts, "
              "or leaves fewer than the minimum."),
            social,
        )
        social_desc.setWordWrap(True)
        social_layout.addWidget(social_desc, 0, 0, 1, 2)
        self.add_config_entry(
            social, social_layout, "social_min_surviving_items", _("Minimum Posts Kept"), 1,
        )
        self.add_config_entry(
            social, social_layout, "social_max_rejection_ratio", _("Maximum Fraction Discarded"), 2,
        )
        outer.addWidget(social)
        outer.addStretch()
        scroll.setWidget(content)

    def create_tts_tab(self):
        scroll = QScrollArea(self.tts_tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ── Common fields ─────────────────────────────────────────────
        common_frame = QFrame(content)
        common_layout = QGridLayout(common_frame)
        common_layout.setContentsMargins(0, 0, 0, 0)

        # Provider combo
        common_layout.addWidget(
            QLabel(_("TTS Provider:"), common_frame), 0, 0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._provider_combo = QComboBox(common_frame)
        # A compiled build contains Coqui only. The config file is shared with
        # source checkouts, so the build leaves the saved provider untouched.
        providers = ("coqui",) if IS_BUILD else ("coqui", "kokoro", "f5tts", "maskgct", "piper", "zonos")
        for value in providers:
            self._provider_combo.addItem(value)
        current = "coqui" if IS_BUILD else (getattr(config, "tts_provider", "coqui") or "coqui")
        self._provider_combo.setCurrentText(current)
        self._provider_combo.currentTextChanged.connect(self._on_tts_provider_changed)
        common_layout.addWidget(self._provider_combo, 0, 1, Qt.AlignmentFlag.AlignLeft)
        if not IS_BUILD:
            self.config_vars["tts_provider"] = (self._provider_combo, "combo")

        self.add_config_entry(common_frame, common_layout, "llm_model_name", _("LLM Model Name"), 1)
        self.add_config_checkbox(
            common_frame, common_layout,
            "llm_use_streaming", _("Stream LLM responses (Ollama NDJSON)"), 2,
        )
        self.add_config_checkbox(
            common_frame, common_layout,
            "llm_stream_redundancy",
            _("Stop LLM on repetitive output (streaming redundancy)"), 3,
        )
        self.add_config_entry(common_frame, common_layout, "max_chunk_tokens", _("Max Chunk Tokens"), 4)
        self.add_config_entry(
            common_frame, common_layout, "llm_thinking_budget_chars",
            _("LLM Thinking Budget (characters, blank for no limit)"), 5,
        )
        main_layout.addWidget(common_frame)
        main_layout.addWidget(self._build_tts_topics_group(content))

        # ── Coqui section ─────────────────────────────────────────────
        self._coqui_section = QGroupBox(_("Coqui TTS"), content)
        coqui_layout = QGridLayout(self._coqui_section)
        if IS_BUILD:
            coqui_layout.addWidget(QLabel(_("Included in this build."), self._coqui_section), 0, 0)
        else:
            self.add_config_entry(
                self._coqui_section, coqui_layout,
                "coqui_tts_location", _("TTS Library Path"), 0,
            )
        main_layout.addWidget(self._coqui_section)

        # ── Kokoro section ────────────────────────────────────────────
        self._kokoro_section = QGroupBox(_("Kokoro TTS"), content)
        kokoro_layout = QGridLayout(self._kokoro_section)

        kokoro_layout.addWidget(
            QLabel(_("Voice:"), self._kokoro_section), 0, 0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._kokoro_voice_combo = QComboBox(self._kokoro_section)
        try:
            from tts.providers.kokoro import KOKORO_VOICES
            self._kokoro_voice_combo.addItems(KOKORO_VOICES)
        except Exception:
            self._kokoro_voice_combo.addItem("af_heart")
        saved_voice = getattr(config, "kokoro_voice", "af_heart") or "af_heart"
        idx = self._kokoro_voice_combo.findText(saved_voice)
        self._kokoro_voice_combo.setCurrentIndex(max(idx, 0))
        kokoro_layout.addWidget(self._kokoro_voice_combo, 0, 1, Qt.AlignmentFlag.AlignLeft)
        self.config_vars["kokoro_voice"] = (self._kokoro_voice_combo, "combo")

        self.add_config_entry(
            self._kokoro_section, kokoro_layout,
            "kokoro_model", _("Model"), 1,
        )
        main_layout.addWidget(self._kokoro_section)

        # ── F5-TTS section ────────────────────────────────────────────
        self._f5tts_section = QGroupBox(_("F5-TTS"), content)
        f5_layout = QGridLayout(self._f5tts_section)
        self.add_config_filepath_entry(
            self._f5tts_section, f5_layout,
            "f5tts_reference_audio", _("Reference Audio (.wav)"), 0,
            _("Audio files") + " (*.wav *.mp3 *.flac)",
        )
        self.add_config_entry(
            self._f5tts_section, f5_layout,
            "f5tts_reference_text", _("Reference Text (optional)"), 1,
        )
        self.add_config_entry(
            self._f5tts_section, f5_layout,
            "f5tts_model", _("Model"), 2,
        )
        main_layout.addWidget(self._f5tts_section)

        # ── MaskGCT section ───────────────────────────────────────────
        self._maskgct_section = QGroupBox(_("MaskGCT / Amphion"), content)
        mgct_layout = QGridLayout(self._maskgct_section)
        self.add_config_filepath_entry(
            self._maskgct_section, mgct_layout,
            "maskgct_reference_audio", _("Reference Audio (.wav)"), 0,
            _("Audio files") + " (*.wav *.mp3 *.flac)",
        )
        self.add_config_entry(
            self._maskgct_section, mgct_layout,
            "maskgct_language", _("Language Code"), 1,
        )
        main_layout.addWidget(self._maskgct_section)

        # ── Zonos section ─────────────────────────────────────────────
        self._zonos_section = QGroupBox(_("Zonos / Zyphra"), content)
        zonos_layout = QGridLayout(self._zonos_section)
        self.add_config_filepath_entry(
            self._zonos_section, zonos_layout,
            "zonos_reference_audio", _("Reference Audio (10–30 s)"), 0,
            _("Audio files") + " (*.wav *.mp3 *.flac)",
        )
        self.add_config_entry(
            self._zonos_section, zonos_layout,
            "zonos_model", _("Model (HuggingFace ID)"), 1,
        )
        self.add_config_entry(
            self._zonos_section, zonos_layout,
            "zonos_language", _("Default Language Code"), 2,
        )
        main_layout.addWidget(self._zonos_section)

        # ── Piper section ─────────────────────────────────────────────
        self._piper_section = QGroupBox(_("Piper TTS"), content)
        piper_layout = QGridLayout(self._piper_section)
        self.add_config_filepath_entry(
            self._piper_section, piper_layout,
            "piper_model_path", _("Model Path (.onnx, optional)"), 0,
            _("ONNX models") + " (*.onnx)",
        )
        self.add_config_dirpath_entry(
            self._piper_section, piper_layout,
            "piper_voices_dir", _("Voices Cache Directory"), 1,
        )

        piper_layout.addWidget(
            QLabel(_("Quality:"), self._piper_section), 2, 0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._piper_quality_combo = QComboBox(self._piper_section)
        for q in ("x_low", "low", "medium", "high"):
            self._piper_quality_combo.addItem(q)
        saved_q = getattr(config, "piper_quality", "medium") or "medium"
        self._piper_quality_combo.setCurrentText(saved_q)
        piper_layout.addWidget(self._piper_quality_combo, 2, 1, Qt.AlignmentFlag.AlignLeft)
        self.config_vars["piper_quality"] = (self._piper_quality_combo, "combo")

        self.add_config_checkbox(
            self._piper_section, piper_layout,
            "piper_auto_download", _("Auto-download voice for language"), 3,
        )
        main_layout.addWidget(self._piper_section)

        main_layout.addStretch()
        scroll.setWidget(content)

        tab_layout = QVBoxLayout(self.tts_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

        # Apply initial visibility
        self._on_tts_provider_changed(current)

    def create_playlist_options_tab(self):
        layout = QVBoxLayout(self.playlist_options_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        group = QGroupBox(_("Track Exclusion Filters"), self.playlist_options_tab)
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(6)

        desc = QLabel(
            _("Tracks whose file path contains any of these strings (case-insensitive) will be excluded from playlists."),
            group,
        )
        desc.setWordWrap(True)
        group_layout.addWidget(desc)

        self._exclusions_list = QListWidget(group)
        for entry in app_info_cache.get(TRACK_EXCLUSIONS_KEY, DEFAULT_TRACK_EXCLUSIONS):
            self._exclusions_list.addItem(entry)
        group_layout.addWidget(self._exclusions_list)

        add_row = QWidget(group)
        add_layout = QHBoxLayout(add_row)
        add_layout.setContentsMargins(0, 0, 0, 0)
        self._exclusion_entry = QLineEdit(add_row)
        self._exclusion_entry.setPlaceholderText(_("New exclusion string..."))
        self._exclusion_entry.returnPressed.connect(self._add_exclusion)
        add_layout.addWidget(self._exclusion_entry)
        add_btn = QPushButton(_("Add"), add_row)
        add_btn.clicked.connect(self._add_exclusion)
        add_layout.addWidget(add_btn)
        remove_btn = QPushButton(_("Remove Selected"), add_row)
        remove_btn.clicked.connect(self._remove_exclusion)
        add_layout.addWidget(remove_btn)
        group_layout.addWidget(add_row)

        layout.addWidget(group)

        limits_group = QGroupBox(_("Group Limits"), self.playlist_options_tab)
        limits_layout = QGridLayout(limits_group)
        limits_layout.setSpacing(6)

        limits_desc = QLabel(
            _("When sorting by a group (composer, artist, album, etc.), stop playback after reaching either limit. Set to 0 to disable."),
            limits_group,
        )
        limits_desc.setWordWrap(True)
        limits_layout.addWidget(limits_desc, 0, 0, 1, 2)

        limits_layout.addWidget(QLabel(_("Max tracks per group:"), limits_group), 1, 0)
        self._group_max_tracks_spin = QSpinBox(limits_group)
        self._group_max_tracks_spin.setRange(0, 9999)
        self._group_max_tracks_spin.setSpecialValueText(_("Unlimited"))
        self._group_max_tracks_spin.setValue(app_info_cache.get(GROUP_MAX_TRACKS_KEY, 0))
        limits_layout.addWidget(self._group_max_tracks_spin, 1, 1)

        limits_layout.addWidget(QLabel(_("Max minutes per group:"), limits_group), 2, 0)
        self._group_max_minutes_spin = QSpinBox(limits_group)
        self._group_max_minutes_spin.setRange(0, 9999)
        self._group_max_minutes_spin.setSpecialValueText(_("Unlimited"))
        self._group_max_minutes_spin.setValue(app_info_cache.get(GROUP_MAX_MINUTES_KEY, 0))
        limits_layout.addWidget(self._group_max_minutes_spin, 2, 1)

        layout.addWidget(limits_group)
        layout.addStretch()

    def _add_exclusion(self):
        text = self._exclusion_entry.text().strip()
        if not text:
            return
        existing = [self._exclusions_list.item(i).text() for i in range(self._exclusions_list.count())]
        if text not in existing:
            self._exclusions_list.addItem(text)
        self._exclusion_entry.clear()

    def _remove_exclusion(self):
        for item in self._exclusions_list.selectedItems():
            self._exclusions_list.takeItem(self._exclusions_list.row(item))

    def _on_tts_provider_changed(self, provider_value: str):
        sections = {
            "coqui":   self._coqui_section,
            "kokoro":  self._kokoro_section,
            "f5tts":   self._f5tts_section,
            "maskgct": self._maskgct_section,
            "zonos":   self._zonos_section,
            "piper":   self._piper_section,
        }
        for key, section in sections.items():
            section.setVisible(key == provider_value)

    def _build_tts_topics_group(self, parent):
        group = QGroupBox(_("Keep a Recording of These Topics"), parent)
        layout = QGridLayout(group)
        desc = QLabel(_("Spoken audio for a checked topic is saved so it can be replayed."), group)
        desc.setWordWrap(True)
        layout.addWidget(desc, 0, 0, 1, 2)
        saved = set(config.save_tts_output_topics or [])
        for index, topic in enumerate(Topic):
            box = QCheckBox(topic.translate(), group)
            box.setChecked(topic.value in saved)
            layout.addWidget(box, 1 + index // 2, index % 2)
            self._tts_topic_checks[topic.value] = box
        return group

    def _begin_scroll_tab(self, tab):
        scroll = QScrollArea(tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        return scroll, content, outer

    def add_string_list(self, parent, key, items, placeholder, browse=None, kind="list"):
        """Editable list of strings. *kind* ``trust`` parses ``name: score`` lines into a dict."""
        container = QWidget(parent)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        listing = QListWidget(container)
        listing.setMinimumHeight(72)
        listing.setMaximumHeight(120)
        for item in items or []:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                listing.addItem(text)
        layout.addWidget(listing)

        row = QWidget(container)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        entry = QLineEdit(row)
        entry.setPlaceholderText(placeholder)
        row_layout.addWidget(entry)

        def _add_text(text):
            text = (text or "").strip()
            if not text:
                return
            existing = [listing.item(i).text() for i in range(listing.count())]
            if text not in existing:
                listing.addItem(text)
            entry.clear()

        add_btn = QPushButton(_("Add"), row)
        add_btn.clicked.connect(lambda: _add_text(entry.text()))
        entry.returnPressed.connect(lambda: _add_text(entry.text()))
        row_layout.addWidget(add_btn)
        if browse == "dir":
            browse_btn = QPushButton(_("Browse"), row)

            def _browse():
                path = QFileDialog.getExistingDirectory(self, placeholder)
                if path:
                    _add_text(path)

            browse_btn.clicked.connect(_browse)
            row_layout.addWidget(browse_btn)
        remove_btn = QPushButton(_("Remove Selected"), row)

        def _remove():
            for item in listing.selectedItems():
                listing.takeItem(listing.row(item))

        remove_btn.clicked.connect(_remove)
        row_layout.addWidget(remove_btn)
        layout.addWidget(row)
        self._list_editors[key] = (listing, kind)
        return container

    def _secret_entry(self, key):
        widget, kind = self.config_vars[key]
        if kind == "entry":
            widget.setEchoMode(QLineEdit.EchoMode.Password)

    def _list_values(self, key):
        listing, _kind = self._list_editors[key]
        return [
            listing.item(i).text().strip()
            for i in range(listing.count())
            if listing.item(i).text().strip()
        ]

    def _config_field_text(self, key):
        """Text for a settings field.

        A directory that failed to load (``~`` not expanded, or not created yet)
        leaves the runtime value empty while the file still holds what was typed.
        Show that text so the field is not blank.
        """
        value = config.get_config_value(key)
        if value is None or value == "":
            raw = config.dict.get(key) if isinstance(getattr(config, "dict", None), dict) else None
            if isinstance(raw, str):
                return raw
        return "" if value is None else str(value)

    def _value_from_entry(self, key, text):
        """Keep numbers as numbers so an unchanged field is not rewritten as text."""
        current = config.get_config_value(key)
        if key == "llm_thinking_budget_chars":
            stripped = text.strip()
            return int(stripped) if stripped else None
        if isinstance(text, str) and text.strip() == "" and current is None:
            return None
        if isinstance(current, bool):
            return text
        if isinstance(current, int):
            try:
                return int(text.strip())
            except (TypeError, ValueError):
                return text
        if isinstance(current, float):
            try:
                return float(text.strip())
            except (TypeError, ValueError):
                return text
        return text

    def add_config_entry(self, parent, layout, key, label_text, row):
        label = QLabel(label_text, parent)
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        entry = QLineEdit(parent)
        entry.setMinimumWidth(320)
        entry.setText(self._config_field_text(key))
        layout.addWidget(entry, row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.config_vars[key] = (entry, "entry")

    def add_config_filepath_entry(self, parent, layout, key, label_text, row, file_filter=""):
        """A config entry row with an inline Browse button for file paths."""
        label = QLabel(label_text, parent)
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        row_widget = QWidget(parent)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        entry = QLineEdit(row_widget)
        entry.setMinimumWidth(260)
        entry.setText(self._config_field_text(key))
        row_layout.addWidget(entry)

        browse_btn = QPushButton(_("Browse"), row_widget)
        _filter = file_filter

        def _browse():
            path, _ = QFileDialog.getOpenFileName(self, label_text, "", _filter)
            if path:
                entry.setText(path)

        browse_btn.clicked.connect(_browse)
        row_layout.addWidget(browse_btn)

        layout.addWidget(row_widget, row, 1, Qt.AlignmentFlag.AlignLeft)
        self.config_vars[key] = (entry, "entry")

    def add_config_dirpath_entry(self, parent, layout, key, label_text, row):
        """A config entry row with an inline Browse button for directory paths."""
        label = QLabel(label_text, parent)
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        row_widget = QWidget(parent)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        entry = QLineEdit(row_widget)
        entry.setMinimumWidth(260)
        entry.setText(self._config_field_text(key))
        row_layout.addWidget(entry)

        browse_btn = QPushButton(_("Browse"), row_widget)

        def _browse():
            path = QFileDialog.getExistingDirectory(self, label_text)
            if path:
                entry.setText(path)

        browse_btn.clicked.connect(_browse)
        row_layout.addWidget(browse_btn)

        layout.addWidget(row_widget, row, 1, Qt.AlignmentFlag.AlignLeft)
        self.config_vars[key] = (entry, "entry")

    def add_config_value_combo(self, parent, layout, key, label_text, row, options):
        """A combo whose labels are translated but whose stored values are not.

        *options* is a list of ``(value, label)`` pairs. The value travels as item
        data rather than as the visible text, so what gets written to the config
        stays the same whatever language the window is displayed in.
        """
        label = QLabel(label_text, parent)
        layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        combo = QComboBox(parent)
        for value, option_label in options:
            combo.addItem(option_label, value)
        index = combo.findData(config.get_config_value(key))
        combo.setCurrentIndex(index if index >= 0 else 0)
        layout.addWidget(combo, row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.config_vars[key] = (combo, "combo_value")

    def add_config_checkbox(self, parent, layout, key, label_text, row):
        checkbox = QCheckBox(label_text, parent)
        val = config.get_config_value(key)
        checkbox.setChecked(bool(val))
        layout.addWidget(checkbox, row, 0, 1, 2, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.config_vars[key] = (checkbox, "checkbox")

    def confirm_close(self):
        if config.has_changes():
            res = self.app_actions.alert(
                _("Close Configuration"),
                _("Do you want to close the configuration window?\nAny unsaved changes will be lost."),
                kind="askokcancel",
                master=self,
            )
            if res:
                self.on_closing()
        else:
            self.on_closing()

    def closeEvent(self, event):
        if config.has_changes():
            res = self.app_actions.alert(
                _("Close Configuration"),
                _("Do you want to close the configuration window?\nAny unsaved changes will be lost."),
                kind="askokcancel",
                master=self,
            )
            if not res:
                event.ignore()
                return
        self.master = None
        if ConfigurationWindow.top_level is self:
            ConfigurationWindow.top_level = None
        event.accept()

    @require_password(ProtectedActions.EDIT_CONFIGURATION)
    def save_config(self):
        try:
            for key, (widget, kind) in self.config_vars.items():
                if kind == "checkbox":
                    config.set_config_value(key, widget.isChecked())
                elif kind == "combo":
                    config.set_config_value(key, widget.currentText())
                elif kind == "combo_value":
                    config.set_config_value(key, widget.currentData())
                else:
                    config.set_config_value(key, self._value_from_entry(key, widget.text()))

            for key, (_listing, kind) in self._list_editors.items():
                values = self._list_values(key)
                if kind == "trust":
                    parsed = {}
                    for line in values:
                        name, sep, score = line.partition(":")
                        if not sep or not name.strip():
                            raise ValueError(
                                _("News source trustworthiness must look like \"bbc-news: 0.5\".")
                            )
                        parsed[name.strip()] = float(score.strip())
                    config.set_config_value(key, parsed)
                else:
                    config.set_config_value(key, values)

            muse = dict(config.muse_config or {})
            for key, widget, kind in self._muse_inputs:
                if kind == "bool":
                    muse[key] = widget.isChecked()
                elif kind == "int":
                    muse[key] = int(widget.text().strip())
                else:
                    muse[key] = float(widget.text().strip())
            config.set_config_value("muse_config", muse)

            checked_topics = [
                topic.value for topic in Topic
                if self._tts_topic_checks[topic.value].isChecked()
            ]
            existing_topics = list(config.save_tts_output_topics or [])
            config.set_config_value(
                "save_tts_output_topics",
                existing_topics if set(checked_topics) == set(existing_topics) else checked_topics,
            )

            language_learning_languages = []
            for i in range(self._language_learning_list.count()):
                code, _sep, level = self._language_learning_list.item(i).text().partition(":")
                language_learning_languages.append({
                    "language_code": code.strip(),
                    "level": level.strip(),
                })
            config.set_config_value("muse_language_learning_languages", language_learning_languages)

            exclusions = [
                self._exclusions_list.item(i).text()
                for i in range(self._exclusions_list.count())
            ]
            app_info_cache.set(TRACK_EXCLUSIONS_KEY, exclusions)
            app_info_cache.set(GROUP_MAX_TRACKS_KEY, self._group_max_tracks_spin.value())
            app_info_cache.set(GROUP_MAX_MINUTES_KEY, self._group_max_minutes_spin.value())

            locale_changed = "locale" in config.changed_values
            debug_changed = "debug" in config.changed_values
            if config.save_config():
                if locale_changed:
                    I18N.install_locale(str(config.locale), verbose=False)
                    self.app_actions.toast(
                        _("Configuration saved. Restart to apply the new language "
                          "to windows that are already open.")
                    )
                else:
                    self.app_actions.toast(_("Configuration saved successfully"))
                if debug_changed:
                    from utils.logging_setup import set_logger_level
                    set_logger_level(bool(config.debug))
                    if self.master is not None:
                        suffix = " (Debug)" if config.debug else ""
                        self.master.setWindowTitle(_(" Muse ") + suffix)
            else:
                self.app_actions.alert(
                    _("Error"), _("Failed to save configuration"), kind="error", master=self
                )
        except Exception as e:
            self.app_actions.alert(_("Error"), str(e), kind="error", master=self)

    def on_closing(self):
        self.master = None
        self.close()
