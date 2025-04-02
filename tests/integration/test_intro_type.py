import pytest
import time
import datetime
from muse.muse import Muse
from muse.muse_memory import MuseMemory
from muse.dj_persona import DJPersona

def mktime(dt):
    """Convert datetime to timestamp."""
    return time.mktime(dt.timetuple())

def create_test_persona(last_hello_time=None, last_signoff_time=None):
    """Create a test persona with optional hello and signoff times."""
    persona = DJPersona(
        name="Test DJ",
        voice_name="test_voice",
        language="English",
        language_code="en",
        s="a man",
        tone="friendly",
        characteristics=["energetic", "knowledgeable"],
        system_prompt="You are a friendly DJ.",
        is_mock=True
    )
    persona.last_hello_time = last_hello_time
    persona.last_signoff_time = last_signoff_time
    return persona

@pytest.mark.integration
class TestIntroType:
    @pytest.fixture(autouse=True)
    def setup(self, mock_args):
        """Set up test environment."""
        MuseMemory.load()
        MuseMemory.get_persona_manager().allow_mock_personas = True
        MuseMemory.get_persona_manager().set_current_persona("test_voice")
        
        # Set up mock args with placeholder=True
        mock_args.placeholder = True  # Set placeholder=True specifically for these tests
        self.muse = Muse(mock_args, None)  # library_data can be None when placeholder is True
        
        # Use a fixed reference time: 2024-03-20 12:00:00
        self.reference_time = datetime.datetime(2024, 3, 20, 12, 0, 0)
        self.reference_timestamp = mktime(self.reference_time)

    def test_first_time_introduction(self):
        """Test case for first-time introduction."""
        persona = create_test_persona()
        result = self.muse._determine_intro_type(self.reference_timestamp, persona)
        assert result == "intro"

    def test_long_absence(self):
        """Test case for long absence (more than 6 hours since both hello and signoff)."""
        last_interaction = mktime(self.reference_time.replace(hour=5, minute=0))
        persona = create_test_persona(
            last_hello_time=last_interaction,
            last_signoff_time=last_interaction
        )
        result = self.muse._determine_intro_type(self.reference_timestamp, persona)
        assert result == "intro"

    def test_recent_return(self):
        """Test case for recent return (1-6 hours since signoff, more than 6 hours since hello)."""
        persona = create_test_persona(
            last_hello_time=mktime(self.reference_time.replace(hour=5, minute=0)),
            last_signoff_time=mktime(self.reference_time.replace(hour=9, minute=0))
        )
        result = self.muse._determine_intro_type(self.reference_timestamp, persona)
        assert result == "reintro"

    def test_very_recent_return(self):
        """Test case for very recent return (less than 1 hour since signoff)."""
        persona = create_test_persona(
            last_hello_time=mktime(self.reference_time.replace(hour=5, minute=0)),
            last_signoff_time=mktime(self.reference_time.replace(hour=11, minute=30))
        )
        result = self.muse._determine_intro_type(self.reference_timestamp, persona)
        assert result is None

    def test_sleeping_hours_case(self):
        """Test case for sleeping hours (last signoff at 11 PM, current time 6 AM)."""
        last_signoff = mktime(self.reference_time.replace(hour=23, minute=0))
        current_time = mktime(self.reference_time.replace(hour=6, minute=0)) + 86400  # Add 24 hours
        persona = create_test_persona(
            last_hello_time=mktime(self.reference_time.replace(hour=17, minute=0)),
            last_signoff_time=last_signoff
        )
        result = self.muse._determine_intro_type(current_time, persona)
        assert result == "intro"

    def test_recent_hello_and_signoff(self):
        """Test case for recent hello and signoff (both within 6 hours)."""
        persona = create_test_persona(
            last_hello_time=mktime(self.reference_time.replace(hour=9, minute=0)),
            last_signoff_time=mktime(self.reference_time.replace(hour=9, minute=0))
        )
        result = self.muse._determine_intro_type(self.reference_timestamp, persona)
        assert result == "reintro"

    def test_exactly_six_hours_since_signoff(self):
        """Test case for exactly 6 hours since signoff."""
        persona = create_test_persona(
            last_hello_time=mktime(self.reference_time.replace(hour=5, minute=0)),
            last_signoff_time=mktime(self.reference_time.replace(hour=6, minute=0))
        )
        result = self.muse._determine_intro_type(self.reference_timestamp, persona)
        assert result == "reintro"

    def test_exactly_one_hour_since_signoff(self):
        """Test case for exactly 1 hour since signoff."""
        persona = create_test_persona(
            last_hello_time=mktime(self.reference_time.replace(hour=5, minute=0)),
            last_signoff_time=mktime(self.reference_time.replace(hour=11, minute=0))
        )
        result = self.muse._determine_intro_type(self.reference_timestamp, persona)
        assert result is None 