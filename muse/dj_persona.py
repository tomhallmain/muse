"""DJ Persona management for the Muse application."""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
import time

from extensions.llm import LLMResult
from tts.speakers import speakers
from utils.config import config
from utils.logging_setup import get_logger
from utils.utils import Utils
from utils.translations import I18N, SUPPORTED_LANGUAGE_CODES

logger = get_logger(__name__)

_ = I18N._

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
    last_hello_time: Optional[float] = None
    last_signoff_time: Optional[float] = None
    artwork_paths: Optional[List[str]] = None
    is_mock: bool = False

    def __post_init__(self):
        if self.context is None:
            self.context = []
        if self.characteristics is None:
            self.characteristics = []
        if not hasattr(self, "is_mock"):
            self.is_mock = False
            
        # Validate language code
        if self.language_code not in SUPPORTED_LANGUAGE_CODES:
            raise ValueError(f"Invalid language code: {self.language_code}. Must be one of {SUPPORTED_LANGUAGE_CODES}")
        
        if self.voice_name not in speakers:
            try: 
                for speaker in speakers:
                    if Utils.is_similar_strings(speaker, self.voice_name):
                        logger.warning(f"Found similar voice name \"{self.voice_name}\", using valid speaker name \"{speaker}\" instead")
                        self.voice_name = speaker
                        break
            except Exception as e:
                logger.error(f"Error validating voice name: {e}")
                raise ValueError(f"Invalid voice name: {self.voice_name}. Must be one of {list(speakers.keys())}")
        
        if self.artwork_paths is not None:
            test_paths = list(self.artwork_paths)
            for path in test_paths:
                if not Path(path).exists():
                    test_paths.remove(path)
                    logger.warning(f"Artwork path \"{path}\" does not exist, removing it")
            if len(test_paths) == 0:
                logger.error(f"No valid artwork paths found for persona \"{self.name}\", using default artwork")
                self.artwork_paths = None
            else:
                self.artwork_paths = test_paths

    def update_context(self, new_context: List[int]) -> None:
        """Update the context with a new list of integers."""
        old_context_len = len(self.context) if self.context else 0
        self.context = new_context
        # Update last signoff time whenever the persona speaks
        self.set_last_signoff_time()
        logger.info(f"Updated context for {self.name}: {old_context_len} -> {len(new_context)} tokens")

    def set_last_signoff_time(self) -> None:
        """Set the last signoff time to the current time."""
        old_time = self.last_signoff_time
        self.last_signoff_time = time.time()
        if old_time:
            logger.info(f"Updated last signoff time for {self.name}: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(old_time))} -> {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_signoff_time))}")
        else:
            logger.info(f"Set initial signoff time for {self.name}: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.last_signoff_time))}")

    def get_context(self) -> List[int]:
        """Get the current context."""
        logger.info(f"Retrieved context for {self.name}: {len(self.context)} tokens")
        return self.context

    def get_s(self) -> str:
        if self.s is None or self.s.upper() == "M":
            return _("a man")
        elif self.s.upper() == "F" or self.s.upper() == "W":
            return _("a woman")
        else:
            return self.s

    def get_artwork_paths(self) -> Optional[List[str]]:
        return self.artwork_paths if hasattr(self, "artwork_paths") else None

    def get_last_tuned_in_str(self) -> str:
        """Get a human-readable string describing when the listener last tuned in.
        
        Returns:
            str: A translated string like "The listener last tuned in 2 hours ago"
        """
        if self.last_signoff_time:
            time_diff = time.time() - self.last_signoff_time
            num_units, unit = I18N.time_ago(time_diff)
            return _("The listener last tuned in {0} {1} ago").format(num_units, unit)
        return _("The listener last tuned in recently")

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
        logger.info(f"Serializing {self.name} persona with {len(self.context)} tokens of context")
        return {
            "name": self.name,
            "voice_name": self.voice_name,
            "s": self.s,
            "tone": self.tone,
            "characteristics": self.characteristics,
            "system_prompt": self.system_prompt,
            "context": self.context,
            "language": self.language,
            "language_code": self.language_code,
            "last_hello_time": self.last_hello_time,
            "last_signoff_time": self.last_signoff_time
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DJPersona':
        """Create a persona from a dictionary."""
        context_len = len(data.get("context", []))
        logger.info(f"Deserializing {data['name']} persona with {context_len} tokens of contex, last hello time {data.get('last_hello_time')}, last signoff time {data.get('last_signoff_time')}")
        
        return cls(
            name=data["name"],
            voice_name=data["voice_name"],
            s=data["s"],
            tone=data["tone"],
            characteristics=data["characteristics"],
            system_prompt=data["system_prompt"],
            context=data.get("context"),
            language=data.get("language", "English"),
            language_code=data.get("language_code", "en"),
            last_hello_time=data.get("last_hello_time"),
            last_signoff_time=data.get("last_signoff_time")
        )

class DJPersonaManager:
    """Manages DJ personas and their loading/saving."""
    
    def __init__(self):
        self.personas: Dict[str, DJPersona] = {}
        self.current_persona: Optional[DJPersona] = None
        self.allow_mock_personas = False
        self._load_personas()

    def _load_personas(self):
        """Load personas from the config JSON file."""
        try:
            print(f"Loading personas from config, count = {len(config.dj_personas)}")
            for persona_data in config.dj_personas:
                persona = DJPersona.from_dict(persona_data)
                if persona.voice_name not in self.personas:
                    self.personas[persona.voice_name] = persona
                else:
                    logger.warning(f"Persona already exists, skipping: {persona.voice_name}")
        except Exception as e:
            logger.error(f"Error loading personas: {e}")
        
        if len(self.personas) == 0:
            self._create_default_personas()
        
        self.current_persona = self.personas[list(self.personas.keys())[0]]

    def reload_personas(self):
        """Reload personas from the config JSON file."""
        try:
            logger.info(f"Reloading personas from config, count = {len(config.dj_personas)}")
            for persona_data in config.dj_personas:
                persona_new = DJPersona.from_dict(persona_data)
                if persona_new.voice_name not in self.personas:
                    self.personas[persona_new.voice_name] = persona_new
                else:
                    self.personas[persona_new.voice_name].update_from_dict(
                        persona_new, refresh_context=config.dj_persona_refresh_context)
            # Remove mock personas
            for name, persona in self.personas.items():
                if persona.is_mock:
                    logger.warning(f"Removing mock persona: {name}")
                    del self.personas[name]
        except Exception as e:
            logger.error(f"Error reloading personas: {e}")

    def _create_default_personas(self):
        """Create default personas if none exist."""
        default_personas = [
            {
                "name": "Royston",
                "voice_name": "Royston Min",
                "s": "M",
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
                "s": "F",
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
                "s": "M",
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
        persona = self.personas.get(voice_name)
        if persona:
            return persona
        elif hasattr(self, "allow_mock_personas") and self.allow_mock_personas:
            logger.warning(f"Mock persona not found, creating new: {voice_name}")
            persona = DJPersona(
                name=voice_name,
                voice_name=voice_name,
                s="a man",
                tone="neutral",
                characteristics=[],
                system_prompt="",
                language="English",
                language_code="en"
            )
            self.personas[voice_name] = persona
            return persona
        else:
            logger.error(f"Persona not found: {voice_name}")
            return None

    def set_current_persona(self, voice_name: str) -> Optional[DJPersona]:
        """Set the current persona by voice name."""
        persona = self.get_persona(voice_name)
        if persona:
            self.current_persona = persona
        return persona

    def get_current_persona(self) -> Optional[DJPersona]:
        """Get the current persona."""
        return self.current_persona

    def update_context(self, llm_result: Optional[LLMResult]):
        """Update the current persona's context with new context from LLM response."""
        if self.current_persona:
            if llm_result:
                if llm_result.context_provided:
                    # NOTE context may not have been provided to the LLM query
                    # initialily, so if we updated using this context it would be
                    # wiping the old context.
                    self.current_persona.update_context(llm_result.context)
                else:
                    # Update last signoff time whenever the persona speaks
                    self.current_persona.set_last_signoff_time()

    def get_context_and_system_prompt(self) -> Tuple[List[int], str]:
        """Get the current persona's context and system prompt."""
        try:
            return (
                self.current_persona.get_context() if self.current_persona else [],
                self.current_persona.system_prompt if self.current_persona else None
                # Default system prompt is used if no persona is selected for some reason
            ) 
        except Exception as e:
            logger.error(f"Error getting context and system prompt: {e}")
            return ([], None)

    def save_personas_to_config(self):
        """Save all personas to the configuration file."""
        try:
            # Convert personas to dict format for config
            personas_data = []
            for persona in self.personas.values():
                personas_data.append(persona.to_dict())
            
            # Update config
            config.dj_personas = personas_data
            success = config.save_config()
            
            if success:
                logger.info(f"Successfully saved {len(personas_data)} personas to configuration")
            else:
                logger.error("Failed to save personas to configuration")
            
            return success
            
        except Exception as e:
            logger.error(f"Error saving personas to config: {e}")
            return False

    def add_persona(self, persona: DJPersona) -> bool:
        """Add a new persona to the manager."""
        try:
            self.personas[persona.voice_name] = persona
            logger.info(f"Added persona: {persona.name} ({persona.voice_name})")
            return True
        except Exception as e:
            logger.error(f"Error adding persona: {e}")
            return False

    def remove_persona(self, voice_name: str) -> bool:
        """Remove a persona from the manager."""
        try:
            if voice_name in self.personas:
                persona = self.personas[voice_name]
                del self.personas[voice_name]
                logger.info(f"Removed persona: {persona.name} ({voice_name})")
                return True
            else:
                logger.warning(f"Persona not found for removal: {voice_name}")
                return False
        except Exception as e:
            logger.error(f"Error removing persona: {e}")
            return False

    def update_persona(self, voice_name: str, updated_persona: DJPersona) -> bool:
        """Update an existing persona in the manager."""
        try:
            if voice_name in self.personas:
                self.personas[voice_name] = updated_persona
                logger.info(f"Updated persona: {updated_persona.name} ({voice_name})")
                return True
            else:
                logger.warning(f"Persona not found for update: {voice_name}")
                return False
        except Exception as e:
            logger.error(f"Error updating persona: {e}")
            return False

    def get_all_personas(self) -> Dict[str, DJPersona]:
        """Get all personas as a dictionary."""
        return self.personas.copy()