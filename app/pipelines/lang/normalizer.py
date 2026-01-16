"""
Text normalization for multilingual document processing.

Handles Unicode normalization, punctuation rules, and script-specific
normalization patterns for consistent keyword matching.
"""

import re
import unicodedata
from typing import Dict, List, Optional


class TextNormalizer:
    """Normalizes text for multilingual keyword matching."""
    
    def __init__(self):
        """Initialize normalizer with script-specific patterns."""
        self._punctuation_patterns = {
            'universal': r'[^\w\s/]',  # Keep / for things like "ship to/consignee"
            'arabic': r'[^\w\s/\u0621-\u064A\u0660-\u0669]',  # Preserve Arabic diacritics
            'cjk': r'[^\w\s/]',  # CJK uses same pattern
            'thai': r'[^\w\s/\u0E00-\u0E7F]',  # Preserve Thai characters
        }
        
        # Script-specific normalization rules
        self._script_rules = {
            'arabic': {
                'normalize_hamza': True,
                'normalize_tatweel': True,  # Remove tatweel (kashida)
                'preserve_diacritics': False,
            },
            'cjk': {
                'normalize_width': True,  # Fullwidth to halfwidth
                'preserve_punctuation': True,
            },
            'thai': {
                'remove_tone_marks': False,  # Keep tone marks for Thai
                'normalize_spacing': True,
            },
            'latin': {
                'case_sensitive': False,
                'remove_accents': False,  # Keep accents for European languages
            }
        }
    
    def normalize_text(self, text: str, script: str = 'latin') -> str:
        """
        Normalize text according to script-specific rules.
        
        Args:
            text: Input text to normalize
            script: Primary script of the text
            
        Returns:
            Normalized text
        """
        if not text:
            return text
        
        # Unicode normalization (NFKC is best for multilingual)
        text = unicodedata.normalize('NFKC', text)
        
        # Apply script-specific rules
        text = self._apply_script_rules(text, script)
        
        # General cleanup
        text = self._general_cleanup(text, script)
        
        return text.strip()
    
    def _apply_script_rules(self, text: str, script: str) -> str:
        """Apply script-specific normalization rules."""
        rules = self._script_rules.get(script, {})
        
        if script == 'arabic':
            if rules.get('normalize_hamza', True):
                # Normalize different forms of hamza to standard hamza
                text = text.replace('\u0625', '\u0627').replace('\u0623', '\u0627').replace('\u0622', '\u0622')
            
            if rules.get('normalize_tatweel', True):
                # Remove tatweel (kashida) character
                text = text.replace('\u0640', '')
        
        elif script == 'cjk':
            if rules.get('normalize_width', True):
                # Convert fullwidth characters to halfwidth
                text = self._normalize_width(text)
        
        elif script == 'thai':
            if rules.get('normalize_spacing', True):
                # Normalize spacing for Thai
                text = re.sub(r'\s+', ' ', text)
        
        elif script == 'latin':
            if not rules.get('case_sensitive', False):
                text = text.lower()
            
            if rules.get('remove_accents', False):
                text = unicodedata.normalize('NFD', text)
                text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        
        return text
    
    def _general_cleanup(self, text: str, script: str) -> str:
        """Apply general cleanup rules."""
        # Get appropriate punctuation pattern
        pattern = self._punctuation_patterns.get(script, self._punctuation_patterns['universal'])
        
        # Replace punctuation with spaces (not removal to preserve word boundaries)
        text = re.sub(pattern, ' ', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text
    
    def _normalize_width(self, text: str) -> str:
        """Convert fullwidth characters to halfwidth (for CJK)."""
        # Fullwidth to halfwidth mapping
        fullwidth_to_halfwidth = {}
        
        # Digits
        for i in range(10):
            fullwidth_to_halfwidth[chr(0xFF10 + i)] = str(i)
        
        # Letters
        for i in range(26):
            fullwidth_to_halfwidth[chr(0xFF21 + i)] = chr(ord('A') + i)
            fullwidth_to_halfwidth[chr(0xFF41 + i)] = chr(ord('a') + i)
        
        # Punctuation (common ones)
        fullwidth_punctuation = {
            '！': '!', '？': '?', '，': ',', '。': '.', '；': ';',
            '：': ':', '（': '(', '）': ')', '【': '[', '】': ']',
            '｛': '{', '｝': '}', '＜': '<', '＞': '>', '／': '/',
            '＼': '\\', '＊': '*', '＆': '&', '％': '%', '＃': '#',
            '＄': '$', '＠': '@', '＋': '+', '－': '-', '＝': '=',
            '＾': '^', '＿': '_', '｀': '`', '｜': '|', '～': '~'
        }
        fullwidth_to_halfwidth.update(fullwidth_punctuation)
        
        # Apply replacements
        for fullwidth, halfwidth in fullwidth_to_halfwidth.items():
            text = text.replace(fullwidth, halfwidth)
        
        return text
    
    def normalize_keywords(self, keywords: List[str], script: str = 'latin') -> List[str]:
        """
        Normalize a list of keywords for consistent matching.
        
        Args:
            keywords: List of keyword strings to normalize
            script: Target script for normalization
            
        Returns:
            List of normalized keywords
        """
        return [self.normalize_text(keyword, script) for keyword in keywords]
    
    def create_keyword_variants(self, keyword: str, script: str = 'latin') -> List[str]:
        """
        Create common variants of a keyword for robust matching.
        
        Args:
            keyword: Base keyword
            script: Target script
            
        Returns:
            List of keyword variants
        """
        variants = [keyword]
        normalized = self.normalize_text(keyword, script)
        
        if normalized not in variants:
            variants.append(normalized)
        
        # Script-specific variants
        if script == 'latin':
            # Add case variants
            if keyword.lower() != keyword:
                variants.append(keyword.lower())
            if keyword.upper() != keyword:
                variants.append(keyword.upper())
            
            # Add space variants
            if ' ' in keyword:
                # Remove spaces
                no_spaces = keyword.replace(' ', '')
                if no_spaces not in variants:
                    variants.append(no_spaces)
                
                # Add hyphen variant
                hyphenated = keyword.replace(' ', '-')
                if hyphenated not in variants:
                    variants.append(hyphenated)
        
        elif script == 'arabic':
            # Add common Arabic variants
            if 'إ' in keyword:
                variants.append(keyword.replace('إ', 'أ'))
            if 'ى' in keyword:
                variants.append(keyword.replace('ى', 'ي'))
        
        elif script == 'cjk':
            # Add simplified/traditional variants if applicable
            # This would need a more sophisticated mapping
            pass
        
        return list(set(variants))  # Remove duplicates
    
    def batch_normalize(self, texts: List[str], script: str = 'latin') -> List[str]:
        """
        Normalize multiple texts efficiently.
        
        Args:
            texts: List of texts to normalize
            script: Target script for normalization
            
        Returns:
            List of normalized texts
        """
        return [self.normalize_text(text, script) for text in texts]
