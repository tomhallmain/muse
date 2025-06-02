import re

from tts.text_cleaner_ruleset import TextCleanerRuleset
from utils.config import config
from utils.translations import I18N
from utils.utils import Utils

_ = I18N._


class Chunker:
    MAX_CHUNK_TOKENS = config.max_chunk_tokens
    cleaner = TextCleanerRuleset()

    def __init__(self, skip_cjk=True):
        """
        Initialize a new Chunker instance.
        
        Args:
            skip_cjk: If True, handle CJK characters (Chinese, Japanese, Korean)
                     by replacing them with descriptive messages as they are not
                     well-handled by the TTS model.
        """
        self.skip_cjk = skip_cjk
        self._cjk_warning_given = False
        self._cjk_scripts_seen = set()
        self._total_chars = 0
        self._cjk_chars = 0

    def _clean_xml(self, text):
        # Remove XML/HTML tags
        cleaned = re.sub(r'<[^>]+>', '', text)
        # Remove any remaining angle brackets
        cleaned = re.sub(r'[<>]', '', cleaned)
        return cleaned.strip()

    def _is_entirely_xml(self, text):
        # Check if text is entirely wrapped in XML/HTML tags
        return bool(re.match(r'^\s*<[^>]+>.*</[^>]+>\s*$', text))

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
            
            # If we haven't given a warning yet and there are CJK scripts, add warning
            if not self._cjk_warning_given and self._cjk_scripts_seen:
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
            return cleaned[1:-1]
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
