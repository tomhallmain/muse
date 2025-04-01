"""DJ Persona management for the Muse application."""

import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

from tts.speakers import speakers
from utils.config import config
from utils.utils import Utils

@dataclass
class DJPersona:
    """Represents a DJ persona with its characteristics and voice settings."""
    name: str
    voice_name: str
    s: str
    tone: str
    characteristics: List[str]
    system_prompt: str
    context: Optional[List[int]] = None
    language: str = "English"
    language_code: str = "en"

    def __post_init__(self):
        if self.context is None:
            self.context = []
        if self.characteristics is None:
            self.characteristics = []
            
        # Validate language code
        valid_language_codes = ["en", "de", "es", "fr", "it"]
        if self.language_code not in valid_language_codes:
            raise ValueError(f"Invalid language code: {self.language_code}. Must be one of {valid_language_codes}")

    def update_context(self, new_context: List[int]) -> None:
        """Update the context with a new list of integers."""
        self.context = new_context

    def get_context(self) -> List[int]:
        """Get the current context."""
        return self.context

    def update_from_dict(self, new_data: 'DJPersona', refresh_context=False) -> None:
        """Update the persona from a new DJPersona object."""
        for key, value in new_data.__dict__.items():
            if key == "context" and not refresh_context:
                # Context needs to be preserved
                continue
            current_value = getattr(self, key)
            if current_value != value:
                setattr(self, key, value)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the persona to a dictionary for serialization."""
        return {
            "name": self.name,
            "voice_name": self.voice_name,
            "s": self.s,
            "tone": self.tone,
            "characteristics": self.characteristics,
            "system_prompt": self.system_prompt,
            "context": self.context,
            "language": self.language,
            "language_code": self.language_code
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DJPersona':
        """Create a persona from a dictionary."""
        return cls(
            name=data["name"],
            voice_name=data["voice_name"],
            s=data["s"],
            tone=data["tone"],
            characteristics=data["characteristics"],
            system_prompt=data["system_prompt"],
            context=data.get("context"),
            language=data.get("language", "English"),
            language_code=data.get("language_code", "en")
        )

class DJPersonaManager:
    """Manages DJ personas and their loading/saving."""
    
    def __init__(self):
        self.personas: Dict[str, DJPersona] = {}
        self.current_persona: Optional[DJPersona] = None
        self._load_personas()

    def _load_personas(self):
        """Load personas from the config JSON file."""
        try:
            print(f"Loading personas from config, count = {len(config.dj_personas)}")
            for persona_data in config.dj_personas:
                persona = DJPersona.from_dict(persona_data)
                self.personas[persona.voice_name] = persona
        except Exception as e:
            Utils.log_red(f"Error loading personas: {e}")
        
        if len(self.personas) == 0:
            self._create_default_personas()
        
        self.current_persona = self.personas[list(self.personas.keys())[0]]

    def reload_personas(self):
        """Reload personas from the config JSON file."""
        try:
            Utils.log(f"Reloading personas from config, count = {len(config.dj_personas)}")
            for persona_data in config.dj_personas:
                persona_new = DJPersona.from_dict(persona_data)
                if persona_new.voice_name not in self.personas:
                    self.personas[persona_new.voice_name] = persona_new
                else:
                    self.personas[persona_new.voice_name].update_from_dict(
                        persona_new, refresh_context=config.dj_persona_refresh_context)
        except Exception as e:
            Utils.log_red(f"Error reloading personas: {e}")

    def _create_default_personas(self):
        """Create default personas if none exist."""
        default_personas = [
            {
                "name": "Royston",
                "voice_name": "Royston Min",
                "s": "a man",
                "tone": "warm and engaging",
                "characteristics": [
                    "classical music expert",
                    "well-read and cultured",
                    "gentle sense of humor",
                    "appreciates musical history"
                ],
                "system_prompt": "You are Royston, a sophisticated DJ with deep knowledge of classical music and cultural history. Your speaking style is warm and engaging, with a gentle sense of humor. You love connecting music to historical events and cultural movements. When discussing tracks, you often reference composers' lives, musical periods, and historical context. Your tone is welcoming but refined, making complex musical concepts accessible to all listeners.",
                "language": "English",
                "language_code": "en"
            },
            {
                "name": "Sofia",
                "voice_name": "Sofia Hellen",
                "s": "a woman",
                "tone": "energetic and passionate",
                "characteristics": [
                    "contemporary music enthusiast",
                    "trend-aware",
                    "upbeat and dynamic",
                    "connects music to modern culture"
                ],
                "system_prompt": "You are Sofia, a vibrant and passionate DJ who brings energy to every track. Your style is modern and dynamic, with a keen eye for contemporary music trends and cultural connections. You excel at making listeners feel the emotional impact of music and often draw parallels between songs and current events or popular culture. Your enthusiasm is infectious, and you have a talent for making every song feel like an exciting discovery.",
                "language": "English",
                "language_code": "en"
            },
            {
                "name": "Ludvig",
                "voice_name": "Ludvig Milivoj",
                "s": "a man",
                "tone": "thoughtful and analytical",
                "characteristics": [
                    "baroque music specialist",
                    "technical knowledge",
                    "philosophical approach",
                    "appreciates musical complexity"
                ],
                "system_prompt": "You are Ludvig, a thoughtful and analytical DJ with deep expertise in baroque music. "
                    "Your style is intellectual yet accessible, often exploring the technical aspects of music while maintaining an engaging narrative. "
                    "You have a philosophical approach to music, frequently connecting songs to broader themes of human experience. "
                    "Your commentary is rich with musical terminology but always explained in a way that enhances rather than overwhelms the listening experience.",
                "language": "German",
                "language_code": "de"
            }
        ]
        
        # Create the configs directory if it doesn't exist
        Path("configs").mkdir(exist_ok=True)

        # Load the default personas
        for persona_data in default_personas:
            persona = DJPersona.from_dict(persona_data)
            self.personas[persona.voice_name] = persona

    def get_persona(self, voice_name: str) -> Optional[DJPersona]:
        """Get a persona by voice name."""
        return self.personas.get(voice_name)

    def set_current_persona(self, voice_name: str) -> Optional[DJPersona]:
        """Set the current persona by voice name."""
        persona = self.get_persona(voice_name)
        if persona:
            self.current_persona = persona
        return persona

    def get_current_persona(self) -> Optional[DJPersona]:
        """Get the current persona."""
        return self.current_persona

    def update_context(self, new_context: Optional[List[int]]):
        """Update the current persona's context with new context from LLM response."""
        if self.current_persona:
            self.current_persona.update_context(new_context)

    def get_context_and_system_prompt(self) -> Tuple[List[int], str]:
        """Get the current persona's context and system prompt."""
        try:
            return (
                self.current_persona.get_context() if self.current_persona else [],
                self.current_persona.system_prompt if self.current_persona else None
                # Default system prompt is used if no persona is selected for some reason
            ) 
        except Exception as e:
            Utils.log_red(f"Error getting context and system prompt: {e}")
            return ([], None)
