import os

from tkinter import (
    BOTH, END, WORD, X, LEFT, RIGHT,
    BooleanVar, StringVar,
    scrolledtext, filedialog
)
from tkinter.ttk import (
    Button, Checkbutton, Combobox, Entry,
    Frame, Label, LabelFrame, Style
)

from .base_window import BaseWindow
from .app_style import AppStyle
from lib.multi_display import SmartToplevel
from tts.speakers import speakers
from muse.voice import Voice
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class TTSWindow(BaseWindow):
    '''
    Window for text-to-speech conversion.
    '''
    top_level = None
    DEFAULT_TOPIC = _("Text to Speech")
    
    def __init__(self, master, app_actions, dimensions="800x600"):
        super().__init__()
        TTSWindow.top_level = SmartToplevel(persistent_parent=master, geometry=dimensions)
        TTSWindow.set_title(_("Text to Speech"))
        self.master = TTSWindow.top_level
        self.master.resizable(True, True)
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Initialize voice with default speaker
        self.speaker = "Aaron Dreschner"  # Default speaker
        self.voice = Voice(coqui_named_voice=self.speaker)
        
        self._create_widgets()
        self._layout_widgets()
        
        # Set initial speaker and trigger change handler
        default_index = speakers.index(self.speaker)
        self.speaker_combo.current(default_index)
        self._on_speaker_change(None)
        
    def _create_widgets(self):
        # Text input area
        self.text_frame = LabelFrame(self.master, text=_("Text Input"))
        self.text_input = scrolledtext.ScrolledText(
            self.text_frame, 
            wrap=WORD, 
            height=10,
            bg=AppStyle.BG_COLOR,
            fg=AppStyle.FG_COLOR,
            insertbackground=AppStyle.FG_COLOR
        )
        
        # File input area
        self.file_frame = LabelFrame(self.master, text=_("File Input"))
        self.file_path = StringVar()
        self.file_entry = Entry(self.file_frame, textvariable=self.file_path, state='readonly')
        self.browse_button = Button(self.file_frame, text=_("Browse"), command=self._browse_file)
        
        # Options frame
        self.options_frame = LabelFrame(self.master, text=_("Options"))
        
        # Speaker selection
        self.speaker_var = StringVar(value=self.speaker)
        self.speaker_label = Label(self.options_frame, text=_("Speaker:"))
        self.speaker_combo = Combobox(self.options_frame, textvariable=self.speaker_var, state='readonly')
        self.speaker_combo['values'] = speakers[:]
        self.speaker_combo.bind('<<ComboboxSelected>>', self._on_speaker_change)
        
        # Split on lines option
        self.split_var = BooleanVar(value=False)
        self.split_check = Checkbutton(self.options_frame, text=_("Split on lines"), variable=self.split_var)
        
        # Action buttons
        self.button_frame = Frame(self.master)
        self.speak_text_button = Button(self.button_frame, text=_("Speak Text"), command=self._speak_text)
        self.speak_file_button = Button(self.button_frame, text=_("Speak File"), command=self._speak_file)
        
        # Status area
        self.status_frame = LabelFrame(self.master, text=_("Status"))
        self.status_text = scrolledtext.ScrolledText(
            self.status_frame, 
            wrap=WORD, 
            height=5, 
            state='disabled',
            bg=AppStyle.BG_COLOR,
            fg=AppStyle.FG_COLOR
        )
        
    def _layout_widgets(self):
        # Text input area
        self.text_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.text_input.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # File input area
        self.file_frame.pack(fill=X, padx=5, pady=5)
        self.file_entry.pack(side=LEFT, fill=X, expand=True, padx=5, pady=5)
        self.browse_button.pack(side=RIGHT, padx=5, pady=5)
        
        # Options frame
        self.options_frame.pack(fill=X, padx=5, pady=5)
        self.speaker_label.pack(side=LEFT, padx=5, pady=5)
        self.speaker_combo.pack(side=LEFT, padx=5, pady=5)
        self.split_check.pack(side=LEFT, padx=5, pady=5)
        
        # Action buttons
        self.button_frame.pack(fill=X, padx=5, pady=5)
        self.speak_text_button.pack(side=LEFT, padx=5, pady=5)
        self.speak_file_button.pack(side=LEFT, padx=5, pady=5)
        
        # Status area
        self.status_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.status_text.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
    def _browse_file(self):
        filepath = filedialog.askopenfilename(
            title=_("Select Text File"),
            filetypes=[(_("Text files"), "*.txt"), (_("All files"), "*.*")]
        )
        if filepath:
            self.file_path.set(filepath)
            
    def _on_speaker_change(self, event):
        self.speaker = self.speaker_var.get()
        self.voice = Voice(coqui_named_voice=self.speaker)
        
    def _update_status(self, message: str):
        self.status_text.configure(state='normal')
        self.status_text.insert(END, message + "\n")
        self.status_text.see(END)
        self.status_text.configure(state='disabled')
        
    def _speak_text(self):
        text = self.text_input.get("1.0", END).strip()
        if not text:
            self._update_status(_("Error: No text provided"))
            return
            
        def speak_thread():
            try:
                output_path = self.voice.say(text, topic=TTSWindow.DEFAULT_TOPIC, save_mp3=True)
                if output_path:
                    self._update_status(_("Successfully generated speech file: {}").format(output_path))
                else:
                    self._update_status(_("No output file was generated"))
            except Exception as e:
                self._update_status(_("Error generating speech: {}").format(str(e)))
                
        Utils.start_thread(speak_thread, use_asyncio=False)
            
    def _speak_file(self):
        filepath = self.file_path.get()
        if not filepath:
            self._update_status(_("Error: No file selected"))
            return
            
        # Validate file exists and is readable
        if not os.path.exists(filepath):
            self._update_status(_("Error: File does not exist"))
            return
        if not os.path.isfile(filepath):
            self._update_status(_("Error: Path is not a file"))
            return
        if os.path.getsize(filepath) == 0:
            self._update_status(_("Error: File is empty"))
            return
            
        def speak_thread():
            try:
                # Get the basename without extension for the topic
                topic = os.path.splitext(os.path.basename(filepath))[0]
                if not topic or not topic.strip():  # Fallback if basename is empty
                    topic = TTSWindow.DEFAULT_TOPIC
                    
                output_path = self.voice.speak_file(
                    filepath,
                    topic=topic,
                    save_mp3=True,
                    split_on_each_line=self.split_var.get()
                )
                if output_path:
                    self._update_status(_("Successfully generated speech file: {}").format(output_path))
                else:
                    self._update_status(_("No output file was generated"))
            except Exception as e:
                self._update_status(_("Error generating speech: {}").format(str(e)))
                
        Utils.start_thread(speak_thread, use_asyncio=False)
            
    @staticmethod
    def set_title(extra_text):
        TTSWindow.top_level.title(_("Text to Speech") + " - " + extra_text)

    def on_close(self):
        self.master.destroy()
        if self.voice:
            self.voice.finish_speaking()
        TTSWindow.top_level = None

