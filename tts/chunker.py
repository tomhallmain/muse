import re

from tts.text_cleaner_ruleset import TextCleanerRuleset
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class Chunker:
    """
    Handles text chunking for TTS processing.
    """
    MAX_CHUNK_TOKENS = config.max_chunk_tokens
    cleaner = TextCleanerRuleset()
    
    # Redundancy thresholds and limits
    MIN_SIMILARITY_LENGTH = 20  # Minimum length to trust similarity checking
    REDUNDANCY_TIERS = [
        (300, 1),   # Chunks under 300 chars can be repeated once
        (100, 2),   # Chunks under 100 chars can be repeated twice
        (50, 3),   # Chunks under 50 chars can be repeated three times
    ]

    def __init__(self, skip_cjk=True, skip_redundant=True):
        """
        Initialize a new Chunker instance.
        
        Args:
            skip_cjk: If True, handle CJK characters (Chinese, Japanese, Korean)
                     by replacing them with descriptive messages as they are not
                     well-handled by the TTS model.
            skip_redundant: If True, skip chunks that are highly similar to previously
                          seen chunks to avoid redundant output.
        """
        self.skip_cjk = skip_cjk
        self.skip_redundant = skip_redundant
        self._cjk_warning_given = False
        self._cjk_scripts_seen = set()
        self._total_chars = 0
        self._cjk_chars = 0
        self._seen_chunks = []  # Store previously seen chunks for similarity comparison
        self._redundant_counts = {}  # Track how many times each chunk has been seen

    def _clean_xml(self, text):
        # Remove XML/HTML tags
        cleaned = re.sub(r'<[^>]+>', '', text)
        # Remove any remaining angle brackets
        cleaned = re.sub(r'[<>]', '', cleaned)
        return cleaned.strip()

    def _is_entirely_xml(self, text):
        # Check if text is entirely wrapped in XML/HTML tags
        return bool(re.match(r'^\s*<[^>]+>.*</[^>]+>\s*$', text))

    def _get_redundancy_limit(self, chunk_length):
        """
        Get the maximum number of times a chunk of given length can be repeated.
        
        Args:
            chunk_length: Length of the chunk in characters
            
        Returns:
            int: Maximum number of allowed repetitions
        """
        for threshold, limit in self.REDUNDANCY_TIERS:
            if chunk_length < threshold:
                return limit
        return 0  # No redundancy allowed for chunks above the highest threshold

    def _is_redundant(self, chunk):
        """
        Check if a chunk is redundant by comparing it with previously seen chunks.
        Uses a tiered system based on chunk length to determine allowed repetitions.
        
        Args:
            chunk: The chunk to check for redundancy
            
        Returns:
            bool: True if the chunk is redundant, False otherwise
        """
        if not self.skip_redundant:
            return False
            
        chunk_length = len(chunk)
        
        # Don't trust similarity checking for very short chunks
        if chunk_length < self.MIN_SIMILARITY_LENGTH:
            return False
            
        for seen_chunk in self._seen_chunks:
            if Utils.is_similar_strings(chunk, seen_chunk):
                # Get the redundancy limit for this chunk length
                redundancy_limit = self._get_redundancy_limit(chunk_length)
                
                # Count how many times this chunk has been seen
                current_count = self._redundant_counts.get(chunk, 0)
                
                if current_count < redundancy_limit:
                    # Allow this repetition
                    self._redundant_counts[chunk] = current_count + 1
                    return False
                return True
        return False

    def _clean(self, text, locale=None):
        """
        Clean and validate text chunks.
        
        Args:
            text: The text to clean
            locale: Optional locale for text cleaning
        
        Returns:
            str: Cleaned text, or None if the text should be skipped
        """
        # First clean XML/HTML
        cleaned = self._clean_xml(text)
        # Skip if entirely XML/HTML
        if self._is_entirely_xml(text) and not self.contains_alphanumeric(cleaned):
            return None
            
        # Handle CJK characters
        if self.skip_cjk:
            # Update character counts
            self._total_chars += len(cleaned)
            cjk_chars, script_counts = Utils.count_cjk_characters(cleaned)
            self._cjk_chars += cjk_chars
            
            # Check for CJK scripts
            if cjk_chars > 0:
                if script_counts['chinese'] > 0:
                    self._cjk_scripts_seen.add("Chinese")
                if script_counts['japanese'] > 0:
                    self._cjk_scripts_seen.add("Japanese")
                if script_counts['korean'] > 0:
                    self._cjk_scripts_seen.add("Korean")
            
            # Only warn if CJK is more than 4% of total and at least 5 CJK chars seen
            cjk_ratio = (self._cjk_chars / self._total_chars) if self._total_chars > 0 else 0
            if (not self._cjk_warning_given and self._cjk_scripts_seen and
                self._cjk_chars >= 5 and cjk_ratio > 0.04):
                scripts = [_("Chinese") if "Chinese" in self._cjk_scripts_seen else None,
                          _("Japanese") if "Japanese" in self._cjk_scripts_seen else None,
                          _("Korean") if "Korean" in self._cjk_scripts_seen else None]
                scripts = [s for s in scripts if s is not None]
                script_desc = _(" and ").join(scripts)
                warning = _("*This text contains {0}, I can't read it but it looks interesting*").format(script_desc)
                cleaned = warning + "\n\n" + cleaned
                self._cjk_warning_given = True
            
        # Apply normal cleaning
        cleaned = self.cleaner.clean(cleaned, locale)
        if self.count_tokens(cleaned) > 200 and cleaned.startswith("\"") and cleaned.endswith("\""):
            # The sentence segmentation algorithm does not break on quotes even if they are long.
            cleaned = cleaned[1:-1]
            
        # Check for redundancy
        if cleaned and self._is_redundant(cleaned):
            return None
            
        # Add to seen chunks if not redundant
        if cleaned:
            self._seen_chunks.append(cleaned)
            
        return cleaned

    @staticmethod
    def contains_alphanumeric(text):
        return bool(re.search(r'\w', text))

    def _yield_chunks(self, lines_iterable, is_str=False, split_on_each_line=False, locale=None):
        last_chunk = ""
        chunk = ""
        for line in lines_iterable:
            if split_on_each_line:
                if self.contains_alphanumeric(line):
                    cleaned = self._clean(line.strip(), locale)
                    if cleaned is not None:
                        yield cleaned
                continue
            if line.strip() == "":
                if chunk.strip() != "":
                    if self.contains_alphanumeric(chunk):
                        cleaned = self._clean(chunk.strip(), locale)
                        if cleaned is not None:
                            yield cleaned
                last_chunk = chunk
                chunk = ""
                continue
            if line.startswith("[") or line.startswith("("):
                continue
            if is_str and len(chunk) > 0 and chunk[-1] != " ":
                chunk += " "
            chunk += line
        if chunk != last_chunk and chunk.strip() != "":
            if self.contains_alphanumeric(chunk):
                cleaned = self._clean(chunk.strip(), locale)
                if cleaned is not None:
                    yield cleaned

    @staticmethod
    def count_tokens(chunk):
        return len(chunk.strip().split(" "))

    @staticmethod
    def split_tokens(chunk, size):
        chunk_tokens = chunk.strip().split(" ")
        return [" ".join(chunk_tokens[i: i + size]) for i in range(0, len(chunk_tokens), size)]

    def yield_chunks(self, lines_iterable, is_str=False, split_on_each_line=False, locale=None):
        """
        Yield cleaned text chunks from the input.
        
        Args:
            lines_iterable: Iterable of text lines
            is_str: Whether the input is a string (True) or file (False)
            split_on_each_line: Whether to split on each line
            locale: Optional locale for text cleaning
        """
        for chunk in self._yield_chunks(lines_iterable, is_str=is_str, split_on_each_line=split_on_each_line, locale=locale):
            if self.count_tokens(chunk) > self.MAX_CHUNK_TOKENS:
                for subchunk in self.split_tokens(chunk, size=self.MAX_CHUNK_TOKENS - 1):
                    yield subchunk
            else:
                yield chunk

    def get_chunks(self, filepath, split_on_each_line=False, locale=None):
        """
        Get chunks from a file.
        
        Args:
            filepath: Path to the file to read
            split_on_each_line: Whether to split on each line
            locale: Optional locale for text cleaning
        """
        with open(filepath, 'r', encoding="utf8") as f:
            yield from self.yield_chunks(f, split_on_each_line=split_on_each_line, locale=locale)

    def get_str_chunks(self, text, split_on_each_line=False, locale=None):
        """
        Get chunks from a string.
        
        Args:
            text: The text to process
            split_on_each_line: Whether to split on each line
            locale: Optional locale for text cleaning
        """
        yield from self.yield_chunks(text.split("\n"), is_str=True, split_on_each_line=split_on_each_line, locale=locale)
