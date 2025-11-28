"""Personas Window for managing DJ personas in the Muse application."""

from tkinter import Frame, Label, StringVar, Text, messagebox, BooleanVar, Checkbutton
from tkinter.ttk import Button, Entry, OptionMenu, Treeview, Scrollbar, Notebook
from tkinter.constants import W, E, N, S, BOTH, YES, END
import tkinter.font as fnt

from lib.multi_display import SmartToplevel
from ui.app_style import AppStyle
from ui.auth.password_utils import require_password
from ui.base_window import BaseWindow
from muse.dj_persona import DJPersona, DJPersonaManager
from tts.speakers import speakers
from utils.config import config
from utils.globals import ProtectedActions, PersonaSex
from utils.logging_setup import get_logger
from utils.translations import I18N, SUPPORTED_LANGUAGE_CODES
from utils.utils import Utils

_ = I18N._

logger = get_logger(__name__)

class PersonasWindow(BaseWindow):
    """
    Window for managing DJ personas - creating, editing, and deleting personas.
    """
    top_level = None

    def __init__(self, master, app_actions):
        super().__init__()
        
        # Create and configure top level window
        PersonasWindow.top_level = SmartToplevel(persistent_parent=master, title=_("DJ Personas"), geometry="1200x800")
        PersonasWindow.top_level.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.master = PersonasWindow.top_level
        self.app_actions = app_actions
        
        # Get persona manager from memory
        from muse.muse_memory import muse_memory
        self.persona_manager = muse_memory.get_persona_manager()
        if not self.persona_manager:
            self.persona_manager = DJPersonaManager()
        
        # Configure grid weights for the window
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

        # Main container
        self.main = Frame(self.master, bg=AppStyle.BG_COLOR)
        self.main.grid(column=0, row=0, sticky='nsew', padx=5, pady=5)
        self.main.grid_rowconfigure(0, weight=1)
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_columnconfigure(1, weight=2)  # Give more weight to the content area

        # Sidebar for persona list
        self.sidebar = Frame(self.main, bg=AppStyle.BG_COLOR)
        self.sidebar.grid(column=0, row=0, sticky='nsew', padx=5, pady=5)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(1, weight=1)

        # Content area for persona details
        self.content = Frame(self.main, bg=AppStyle.BG_COLOR)
        self.content.grid(column=1, row=0, sticky='nsew', padx=5, pady=5)
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        # Initialize variables
        self.selected_persona = None
        self.persona_vars = {}
        
        # Create UI elements
        self.create_sidebar()
        self.create_content_area()
        
        # Load personas
        self.refresh_persona_list()
        
        # Set default values for new persona (no persona selected initially)
        self.set_default_persona_values()

    def create_sidebar(self):
        """Create the sidebar with persona list and controls."""
        # Title
        title_label = Label(self.sidebar, text=_("DJ Personas"), font=('Helvetica', 14, 'bold'), 
                          bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR)
        title_label.grid(row=0, column=0, sticky=W, pady=(0, 10))

        # Persona list with scrollbar
        list_frame = Frame(self.sidebar, bg=AppStyle.BG_COLOR)
        list_frame.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        # Treeview for persona list
        self.persona_tree = Treeview(list_frame, columns=('name', 'voice'), show='tree headings', height=15)
        self.persona_tree.heading('#0', text=_('Name'))
        self.persona_tree.heading('name', text=_('Display Name'))
        self.persona_tree.heading('voice', text=_('Voice'))
        self.persona_tree.column('#0', width=100)
        self.persona_tree.column('name', width=120)
        self.persona_tree.column('voice', width=120)
        self.persona_tree.grid(row=0, column=0, sticky='nsew')

        # Scrollbar for treeview
        scrollbar = Scrollbar(list_frame, orient="vertical", command=self.persona_tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.persona_tree.configure(yscrollcommand=scrollbar.set)

        # Bind selection event
        self.persona_tree.bind('<<TreeviewSelect>>', self.on_persona_select)

        # Control buttons
        button_frame = Frame(self.sidebar, bg=AppStyle.BG_COLOR)
        button_frame.grid(row=2, column=0, sticky='ew', pady=(0, 10))

        self.add_btn = Button(button_frame, text=_("Add New"), command=self.add_persona)
        self.add_btn.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        self.edit_btn = Button(button_frame, text=_("Edit"), command=self.edit_persona)
        self.edit_btn.grid(row=0, column=1, sticky='ew', padx=5)

        self.delete_btn = Button(button_frame, text=_("Delete"), command=self.delete_persona)
        self.delete_btn.grid(row=0, column=2, sticky='ew', padx=(5, 0))

        # Configure button frame columns
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)

    def create_content_area(self):
        """Create the content area for persona details."""
        # Create notebook for tabbed interface
        self.notebook = Notebook(self.content)
        self.notebook.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        # Basic info tab
        self.basic_tab = Frame(self.notebook, bg=AppStyle.BG_COLOR)
        self.notebook.add(self.basic_tab, text=_("Basic Info"))

        # Characteristics tab
        self.characteristics_tab = Frame(self.notebook, bg=AppStyle.BG_COLOR)
        self.notebook.add(self.characteristics_tab, text=_("Characteristics"))

        # System prompt tab
        self.prompt_tab = Frame(self.notebook, bg=AppStyle.BG_COLOR)
        self.notebook.add(self.prompt_tab, text=_("System Prompt"))

        # Create tab contents
        self.create_basic_tab()
        self.create_characteristics_tab()
        self.create_prompt_tab()

        # Action buttons
        action_frame = Frame(self.content, bg=AppStyle.BG_COLOR)
        action_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=5)

        self.save_btn = Button(action_frame, text=_("Save Changes"), command=self.save_persona)
        self.save_btn.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        self.cancel_btn = Button(action_frame, text=_("Cancel"), command=self.cancel_edit)
        self.cancel_btn.grid(row=0, column=1, sticky='ew', padx=5)

        self.reload_btn = Button(action_frame, text=_("Reload from Config"), command=self.reload_personas)
        self.reload_btn.grid(row=0, column=2, sticky='ew', padx=(5, 0))

        # Configure action frame columns
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_columnconfigure(1, weight=1)
        action_frame.grid_columnconfigure(2, weight=1)

    def create_basic_tab(self):
        """Create the basic information tab."""
        # Name
        Label(self.basic_tab, text=_("Display Name:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=0, column=0, sticky=W, pady=5)
        self.persona_vars['name'] = StringVar()
        Entry(self.basic_tab, textvariable=self.persona_vars['name'], width=40).grid(row=0, column=1, sticky=W, pady=5, padx=(10, 0))

        # Voice name
        Label(self.basic_tab, text=_("Voice Name:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=1, column=0, sticky=W, pady=5)
        self.persona_vars['voice_name'] = StringVar()
        voice_frame = Frame(self.basic_tab, bg=AppStyle.BG_COLOR)
        voice_frame.grid(row=1, column=1, sticky=W, pady=5, padx=(10, 0))
        
        self.voice_combo = OptionMenu(voice_frame, self.persona_vars['voice_name'], *speakers)
        self.voice_combo.grid(row=0, column=0, sticky=W)

        # Sex
        Label(self.basic_tab, text=_("Sex:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=2, column=0, sticky=W, pady=5)
        self.persona_vars['s'] = StringVar()
        sex_frame = Frame(self.basic_tab, bg=AppStyle.BG_COLOR)
        sex_frame.grid(row=2, column=1, sticky=W, pady=5, padx=(10, 0))
        
        OptionMenu(sex_frame, self.persona_vars['s'], *PersonaSex.get_translated_names()).grid(row=0, column=0, sticky=W)

        # Tone
        Label(self.basic_tab, text=_("Tone:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=3, column=0, sticky=W, pady=5)
        self.persona_vars['tone'] = StringVar()
        Entry(self.basic_tab, textvariable=self.persona_vars['tone'], width=40).grid(row=3, column=1, sticky=W, pady=5, padx=(10, 0))

        # Language
        Label(self.basic_tab, text=_("Language:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=4, column=0, sticky=W, pady=5)
        self.persona_vars['language'] = StringVar()
        Entry(self.basic_tab, textvariable=self.persona_vars['language'], width=40).grid(row=4, column=1, sticky=W, pady=5, padx=(10, 0))

        # Language code
        Label(self.basic_tab, text=_("Language Code:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=5, column=0, sticky=W, pady=5)
        self.persona_vars['language_code'] = StringVar()
        lang_code_frame = Frame(self.basic_tab, bg=AppStyle.BG_COLOR)
        lang_code_frame.grid(row=5, column=1, sticky=W, pady=5, padx=(10, 0))
        
        self.language_code_combo = OptionMenu(lang_code_frame, self.persona_vars['language_code'], *SUPPORTED_LANGUAGE_CODES, command=self.on_language_code_change)
        self.language_code_combo.grid(row=0, column=0, sticky=W)

    def create_characteristics_tab(self):
        """Create the characteristics tab."""
        # Characteristics list
        Label(self.characteristics_tab, text=_("Characteristics:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=0, column=0, sticky=W, pady=5)
        
        # Text area for characteristics
        self.characteristics_text = Text(self.characteristics_tab, height=15, width=60, wrap='word')
        self.characteristics_text.grid(row=1, column=0, columnspan=2, sticky='nsew', pady=5, padx=(10, 0))
        
        # Scrollbar for characteristics text
        char_scrollbar = Scrollbar(self.characteristics_tab, orient="vertical", command=self.characteristics_text.yview)
        char_scrollbar.grid(row=1, column=2, sticky='ns')
        self.characteristics_text.configure(yscrollcommand=char_scrollbar.set)

        # Instructions
        instructions = Label(self.characteristics_tab, 
                           text=_("Enter one characteristic per line. These describe the persona's personality and expertise."),
                           bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=400)
        instructions.grid(row=2, column=0, columnspan=2, sticky=W, pady=5, padx=(10, 0))

        # Configure grid weights
        self.characteristics_tab.grid_rowconfigure(1, weight=1)
        self.characteristics_tab.grid_columnconfigure(0, weight=1)

    def create_prompt_tab(self):
        """Create the system prompt tab."""
        # System prompt
        Label(self.prompt_tab, text=_("System Prompt:"), bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR).grid(row=0, column=0, sticky=W, pady=5)
        
        # Text area for system prompt
        self.prompt_text = Text(self.prompt_tab, height=15, width=60, wrap='word')
        self.prompt_text.grid(row=1, column=0, columnspan=2, sticky='nsew', pady=5, padx=(10, 0))
        
        # Scrollbar for prompt text
        prompt_scrollbar = Scrollbar(self.prompt_tab, orient="vertical", command=self.prompt_text.yview)
        prompt_scrollbar.grid(row=1, column=2, sticky='ns')
        self.prompt_text.configure(yscrollcommand=prompt_scrollbar.set)

        # Instructions
        instructions = Label(self.prompt_tab, 
                           text=_("Enter the system prompt that defines how this persona should behave and speak."),
                           bg=AppStyle.BG_COLOR, fg=AppStyle.FG_COLOR, wraplength=400)
        instructions.grid(row=2, column=0, columnspan=2, sticky=W, pady=5, padx=(10, 0))

        # Configure grid weights
        self.prompt_tab.grid_rowconfigure(1, weight=1)
        self.prompt_tab.grid_columnconfigure(0, weight=1)

    def refresh_persona_list(self):
        """Refresh the persona list in the sidebar."""
        # Clear existing items
        for item in self.persona_tree.get_children():
            self.persona_tree.delete(item)
        
        # Add personas from manager
        for voice_name, persona in self.persona_manager.personas.items():
            self.persona_tree.insert('', 'end', text=persona.name, values=(persona.name, voice_name))

    def on_persona_select(self, event):
        """Handle persona selection in the tree."""
        selection = self.persona_tree.selection()
        if selection:
            item = self.persona_tree.item(selection[0])
            voice_name = item['values'][1]  # Voice name is in the second column
            self.load_persona(voice_name)

    def on_language_code_change(self, event=None):
        """Handle language code selection change."""
        try:
            language_code = self.persona_vars['language_code'].get()
            if language_code:
                # Get the English language name for the selected code
                language_name = Utils.get_english_language_name(language_code)
                # Update the language field with the English name
                self.persona_vars['language'].set(language_name)
        except Exception as e:
            logger.error(f"Error updating language name from code: {e}")

    def set_default_persona_values(self):
        """Set default values for a new persona."""
        # Set default basic info
        self.persona_vars['name'].set(_("New Persona"))
        self.persona_vars['tone'].set(_("friendly and engaging"))
        self.persona_vars['language'].set(_("English"))
        self.persona_vars['language_code'].set("en")
        self.persona_vars['s'].set(PersonaSex.MALE.get_translation())
        
        # Set default characteristics
        default_characteristics = [
            _("music enthusiast"),
            _("knowledgeable about various genres"),
            _("engaging storyteller"),
            _("passionate about sharing music")
        ]
        self.characteristics_text.delete(1.0, END)
        self.characteristics_text.insert(1.0, '\n'.join(default_characteristics))
        
        # Set default system prompt
        default_prompt = _("""You are a knowledgeable and engaging DJ with a passion for music. Your speaking style is friendly and engaging, with a talent for connecting with your audience. You love sharing interesting facts about music, artists, and genres, and you have a gift for making every song feel special and meaningful. When discussing tracks, you often provide context about the artist, the genre, or the cultural significance of the music. Your enthusiasm is infectious, and you have a way of making listeners feel like they're discovering something wonderful together with you.""")
        
        self.prompt_text.delete(1.0, END)
        self.prompt_text.insert(1.0, default_prompt)

    def load_persona(self, voice_name):
        """Load a persona into the form fields."""
        persona = self.persona_manager.get_persona(voice_name)
        if persona:
            self.selected_persona = persona
            
            # Load basic info
            self.persona_vars['name'].set(persona.name)
            self.persona_vars['voice_name'].set(persona.voice_name)
            self.persona_vars['s'].set(PersonaSex.to_translated_display(persona.s))
            self.persona_vars['tone'].set(persona.tone)
            self.persona_vars['language'].set(persona.language)
            self.persona_vars['language_code'].set(persona.language_code)
            
            # Load characteristics
            self.characteristics_text.delete(1.0, END)
            if persona.characteristics:
                self.characteristics_text.insert(1.0, '\n'.join(persona.characteristics))
            
            # Load system prompt
            self.prompt_text.delete(1.0, END)
            self.prompt_text.insert(1.0, persona.system_prompt)

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def add_persona(self):
        """Add a new persona."""
        self.clear_form()
        self.selected_persona = None

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def edit_persona(self):
        """Edit the selected persona."""
        if not self.selected_persona:
            messagebox.showwarning(_("No Selection"), _("Please select a persona to edit."))
            return

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def delete_persona(self):
        """Delete the selected persona."""
        if not self.selected_persona:
            messagebox.showwarning(_("No Selection"), _("Please select a persona to delete."))
            return
        
        result = messagebox.askyesno(_("Confirm Delete"), 
                                   _("Are you sure you want to delete the persona '{}'?").format(self.selected_persona.name))
        if result:
            # Remove from persona manager
            success = self.persona_manager.remove_persona(self.selected_persona.voice_name)
            if success:
                # Save to config
                self.save_personas_to_config()
            else:
                messagebox.showerror(_("Error"), _("Failed to remove persona from manager."))
                return
            
            # Refresh UI
            self.clear_form()
            self.refresh_persona_list()
            messagebox.showinfo(_("Success"), _("Persona deleted successfully."))

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def save_persona(self):
        """Save the current persona."""
        try:
            # Validate required fields
            if not self.persona_vars['name'].get().strip():
                messagebox.showerror(_("Validation Error"), _("Display name is required."))
                return
            
            if not self.persona_vars['voice_name'].get().strip():
                messagebox.showerror(_("Validation Error"), _("Voice name is required."))
                return
            
            if not self.persona_vars['tone'].get().strip():
                messagebox.showerror(_("Validation Error"), _("Tone is required."))
                return
            
            if not self.prompt_text.get(1.0, END).strip():
                messagebox.showerror(_("Validation Error"), _("System prompt is required."))
                return

            # Get characteristics from text area
            characteristics_text = self.characteristics_text.get(1.0, END).strip()
            characteristics = [line.strip() for line in characteristics_text.split('\n') if line.strip()]

            # Convert translated sex value back to legacy value
            try:
                sex_enum = PersonaSex.get_from_translation(self.persona_vars['s'].get())
                sex_value = sex_enum.get_legacy_value()
            except:
                sex_value = "M"  # Default fallback

            # Create or update persona
            persona_data = {
                'name': self.persona_vars['name'].get().strip(),
                'voice_name': self.persona_vars['voice_name'].get().strip(),
                's': sex_value,
                'tone': self.persona_vars['tone'].get().strip(),
                'characteristics': characteristics,
                'system_prompt': self.prompt_text.get(1.0, END).strip(),
                'language': self.persona_vars['language'].get().strip(),
                'language_code': self.persona_vars['language_code'].get()
            }

            # Create persona object
            try:
                persona = DJPersona.from_dict(persona_data)
            except ValueError as e:
                messagebox.showerror(_("Validation Error"), _("Invalid persona data: {}").format(str(e)))
                return
            
            # Add or update in manager
            if self.selected_persona and self.selected_persona.voice_name == persona.voice_name:
                # Update existing persona
                self.persona_manager.update_persona(persona.voice_name, persona)
            else:
                # Add new persona
                self.persona_manager.add_persona(persona)
            
            # Save to config
            self.save_personas_to_config()
            
            # Refresh UI
            self.refresh_persona_list()
            self.selected_persona = persona
            
            messagebox.showinfo(_("Success"), _("Persona saved successfully."))
            
        except Exception as e:
            logger.error(f"Error saving persona: {e}")
            messagebox.showerror(_("Error"), _("Failed to save persona: {}").format(str(e)))

    @require_password(ProtectedActions.EDIT_PERSONAS)
    def save_personas_to_config(self):
        """Save all personas to the configuration file."""
        try:
            success = self.persona_manager.save_personas_to_config()
            if success:
                # Reload personas in manager
                self.persona_manager.reload_personas()
            else:
                messagebox.showerror(_("Error"), _("Failed to save personas to configuration."))
        except Exception as e:
            logger.error(f"Error saving personas to config: {e}")
            messagebox.showerror(_("Error"), _("Failed to save personas to configuration: {}").format(str(e)))

    def cancel_edit(self):
        """Cancel the current edit and reload the selected persona."""
        if self.selected_persona:
            self.load_persona(self.selected_persona.voice_name)
        else:
            self.clear_form()

    def clear_form(self):
        """Clear all form fields."""
        for var in self.persona_vars.values():
            var.set('')
        
        self.characteristics_text.delete(1.0, END)
        self.prompt_text.delete(1.0, END)
        self.selected_persona = None
        
        # Set default values when no persona is selected
        self.set_default_persona_values()

    def reload_personas(self):
        """Reload personas from configuration."""
        try:
            self.persona_manager.reload_personas()
            self.refresh_persona_list()
            self.clear_form()
            messagebox.showinfo(_("Success"), _("Personas reloaded from configuration."))
        except Exception as e:
            logger.error(f"Error reloading personas: {e}")
            messagebox.showerror(_("Error"), _("Failed to reload personas: {}").format(str(e)))

    def on_closing(self):
        """Handle window closing."""
        if self.master is not None:
            self.master.destroy()
        self.has_closed = True
