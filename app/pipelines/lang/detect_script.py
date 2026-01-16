"""
Unicode script detection for language pack routing.

Identifies the dominant script(s) in text to select appropriate language packs.
"""

import re
from typing import Dict, List, Tuple
from collections import Counter


class ScriptDetector:
    """Detects Unicode scripts in text for language pack routing."""
    
    # Unicode ranges for different scripts
    SCRIPT_RANGES = {
        'latin': [
            (0x0041, 0x005A),  # A-Z
            (0x0061, 0x007A),  # a-z
            (0x00C0, 0x00FF),  # Latin-1 Supplement
            (0x0100, 0x017F),  # Latin Extended-A
            (0x0180, 0x024F),  # Latin Extended-B
        ],
        'arabic': [
            (0x0600, 0x06FF),  # Arabic
            (0x0750, 0x077F),  # Arabic Supplement
            (0x08A0, 0x08FF),  # Arabic Extended-A
            (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
            (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
        ],
        'cjk': [
            (0x4E00, 0x9FFF),  # CJK Unified Ideographs
            (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
            (0x20000, 0x2A6DF),  # CJK Unified Ideographs Extension B
            (0x2A700, 0x2B73F),  # CJK Unified Ideographs Extension C
            (0x2B740, 0x2B81F),  # CJK Unified Ideographs Extension D
            (0x2B820, 0x2CEAF),  # CJK Unified Ideographs Extension E
            (0x2CEB0, 0x2EBEF),  # CJK Unified Ideographs Extension F
            (0x3000, 0x303F),  # CJK Symbols and Punctuation
            (0xFF00, 0xFFEF),  # Halfwidth and Fullwidth Forms
        ],
        'hangul': [
            (0xAC00, 0xD7AF),  # Hangul Syllables
            (0x1100, 0x11FF),  # Hangul Jamo
            (0x3130, 0x318F),  # Hangul Compatibility Jamo
            (0xA960, 0xA97F),  # Hangul Jamo Extended-A
            (0xD7B0, 0xD7FF),  # Hangul Jamo Extended-B
        ],
        'thai': [
            (0x0E00, 0x0E7F),  # Thai
        ],
        'cyrillic': [
            (0x0400, 0x04FF),  # Cyrillic
            (0x0500, 0x052F),  # Cyrillic Supplement
            (0x2DE0, 0x2DFF),  # Cyrillic Extended-A
            (0xA640, 0xA69F),  # Cyrillic Extended-B
        ],
        'devanagari': [
            (0x0900, 0x097F),  # Devanagari
            (0xA8E0, 0xA8FF),  # Devanagari Extended
        ],
        'hebrew': [
            (0x0590, 0x05FF),  # Hebrew
        ],
        'bengali': [
            (0x0980, 0x09FF),  # Bengali
        ],
        'tamil': [
            (0x0B80, 0x0BFF),  # Tamil
        ],
        'telugu': [
            (0x0C00, 0x0C7F),  # Telugu
        ],
    }
    
    def __init__(self):
        """Initialize script detector with compiled ranges."""
        self._compiled_ranges = {}
        for script, ranges in self.SCRIPT_RANGES.items():
            self._compiled_ranges[script] = [
                (start, end) for start, end in ranges
            ]
    
    def _get_char_script(self, char: str) -> str:
        """Get the script for a single character."""
        char_code = ord(char)
        
        for script, ranges in self._compiled_ranges.items():
            for start, end in ranges:
                if start <= char_code <= end:
                    return script
        
        return 'unknown'
    
    def detect_scripts(self, text: str) -> Dict[str, int]:
        """
        Count characters by script in the given text.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dictionary mapping script names to character counts
        """
        script_counts = Counter()
        
        for char in text:
            if char.strip():  # Skip whitespace
                script = self._get_char_script(char)
                if script != 'unknown':
                    script_counts[script] += 1
        
        return dict(script_counts)
    
    def get_dominant_script(self, text: str, min_threshold: int = 5) -> Tuple[str, float]:
        """
        Get the dominant script and its confidence.
        
        Args:
            text: Input text to analyze
            min_threshold: Minimum characters required for script detection
            
        Returns:
            Tuple of (script_name, confidence_ratio)
        """
        script_counts = self.detect_scripts(text)
        
        if not script_counts:
            return 'latin', 0.0  # Default fallback
        
        total_chars = sum(script_counts.values())
        if total_chars < min_threshold:
            return 'latin', 0.0  # Default fallback for very short text
        
        # Find the most common script
        dominant_script = max(script_counts.items(), key=lambda x: x[1])
        confidence = dominant_script[1] / total_chars
        
        return dominant_script[0], confidence
    
    def get_script_candidates(self, text: str, min_ratio: float = 0.1) -> List[Tuple[str, float]]:
        """
        Get all scripts that meet minimum ratio threshold.
        
        Args:
            text: Input text to analyze
            min_ratio: Minimum ratio of characters to include script
            
        Returns:
            List of (script_name, ratio) tuples sorted by ratio
        """
        script_counts = self.detect_scripts(text)
        
        if not script_counts:
            return [('latin', 0.0)]
        
        total_chars = sum(script_counts.values())
        if total_chars == 0:
            return [('latin', 0.0)]
        
        candidates = []
        for script, count in script_counts.items():
            ratio = count / total_chars
            if ratio >= min_ratio:
                candidates.append((script, ratio))
        
        # Sort by ratio (descending)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        return candidates if candidates else [('latin', 0.0)]
    
    def is_mixed_script(self, text: str, threshold: float = 0.3) -> bool:
        """
        Check if text contains multiple significant scripts.
        
        Args:
            text: Input text to analyze
            threshold: Minimum ratio for secondary script to be considered significant
            
        Returns:
            True if text has multiple significant scripts
        """
        candidates = self.get_script_candidates(text, min_ratio=threshold)
        return len(candidates) > 1
    
    def get_script_summary(self, text: str) -> Dict:
        """
        Get comprehensive script analysis summary.
        
        Args:
            text: Input text to analyze
            
        Returns:
            Dictionary with detailed script information
        """
        script_counts = self.detect_scripts(text)
        total_chars = sum(script_counts.values())
        
        if total_chars == 0:
            return {
                'total_characters': 0,
                'script_counts': {},
                'dominant_script': 'latin',
                'dominant_confidence': 0.0,
                'is_mixed_script': False,
                'candidates': [('latin', 0.0)]
            }
        
        dominant_script, dominant_confidence = self.get_dominant_script(text)
        candidates = self.get_script_candidates(text)
        
        return {
            'total_characters': total_chars,
            'script_counts': script_counts,
            'dominant_script': dominant_script,
            'dominant_confidence': dominant_confidence,
            'is_mixed_script': self.is_mixed_script(text),
            'candidates': candidates
        }
