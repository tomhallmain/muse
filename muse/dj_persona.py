"""DJ Persona management for the Muse application."""

import json
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from pathlib import Path

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

    def __post_init__(self):
        if self.context is None:
            self.context = []

    @classmethod
    def from_dict(cls, data: Dict) -> 'DJPersona':
        """Create a DJPersona instance from a dictionary."""
        return cls(
            name=data['name'],
            voice_name=data['voice_name'],
            tone=data['tone'],
            characteristics=data['characteristics'],
            system_prompt=data['system_prompt']
        )

    def to_dict(self) -> Dict:
        """Convert the DJPersona to a dictionary."""
        return {
            'name': self.name,
            'voice_name': self.voice_name,
            'tone': self.tone,
            'characteristics': self.characteristics,
            'system_prompt': self.system_prompt,
            'context': self.context
        }

    def update_context(self, new_context: Optional[List[int]]):
        """Update the context with a new list of integers from the LLM response."""
        if new_context is not None:
            self.context = new_context

    def get_context(self) -> List[int]:
        """Get the current context."""
        return self.context

class DJPersonaManager:
    """Manages DJ personas and their loading/saving."""
    
    def __init__(self, personas_file: str = "configs/dj_personas.json"):
        self.personas_file = personas_file
        self.personas: Dict[str, DJPersona] = {}
        self.current_persona: Optional[DJPersona] = None
        self._load_personas()

    def _load_personas(self):
        """Load personas from the JSON file."""
        try:
            with open(self.personas_file, 'r', encoding='utf-8') as f:
                personas_data = json.load(f)
                for persona_data in personas_data:
                    persona = DJPersona.from_dict(persona_data)
                    self.personas[persona.name] = persona
        except FileNotFoundError:
            # Create default personas if file doesn't exist
            self._create_default_personas()
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in personas file: {self.personas_file}")

    def _create_default_personas(self):
        """Create default personas if none exist."""
        default_personas = [
            {
                "name": "Classic DJ",
                "voice_name": "en_US-amy-medium",
                "s": "F",
                "tone": "professional and engaging",
                "characteristics": [
                    "well-informed about music history",
                    "maintains a professional demeanor",
                    "provides interesting context about tracks"
                ],
                "system_prompt": "You are a professional radio DJ with deep knowledge of music history. "
                               "Your role is to provide engaging commentary about the music while maintaining "
                               "a professional and informative tone."
            },
            {
                "name": "Casual DJ",
                "voice_name": "en_US-ryan-medium",
                "s": "M",
                "tone": "friendly and conversational",
                "characteristics": [
                    "relaxed and approachable",
                    "shares personal anecdotes",
                    "interacts naturally with listeners"
                ],
                "system_prompt": "You are a friendly and casual DJ who treats listeners like friends. "
                               "Share personal anecdotes and maintain a conversational tone while discussing music."
            }
        ]
        
        # Create the configs directory if it doesn't exist
        Path("configs").mkdir(exist_ok=True)
        
        # Save default personas
        with open(self.personas_file, 'w', encoding='utf-8') as f:
            json.dump(default_personas, f, indent=4)
        
        # Load the default personas
        for persona_data in default_personas:
            persona = DJPersona.from_dict(persona_data)
            self.personas[persona.name] = persona

    def get_persona(self, name: str) -> Optional[DJPersona]:
        """Get a persona by name."""
        return self.personas.get(name)

    def set_current_persona(self, name: str) -> Optional[DJPersona]:
        """Set the current persona by name."""
        persona = self.get_persona(name)
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
        return (
            self.current_persona.get_context() if self.current_persona else [],
            self.current_persona.system_prompt if self.current_persona else ""
        ) 