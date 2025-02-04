#!/usr/bin/env python3

"""Language handling system"""

import os
from os.path import exists
import glob
import importlib
from typing import Dict, Any, List
from utils import debug_print

DEFAULT_LANGUAGE = 'en'

def get_supported_languages() -> List[str]:
    """
    Scan the languages directory for available language files.
    Returns list of language codes (e.g., ['en', 'de'])
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    lang_files = glob.glob(os.path.join(current_dir, '*_lang.py'))
    return [os.path.basename(f).replace('_lang.py', '') for f in lang_files]

# Get available languages by scanning directory
SUPPORTED_LANGUAGES = get_supported_languages()

class LanguageStrings:
    def __init__(self, strings: Dict[str, Any], name: str = DEFAULT_LANGUAGE):
        self._strings = strings
        self.name = name

    def get(self, *keys: str) -> str:
        """
        Get translated text for the given keys.
        
        Args:
            *keys: Sequence of keys to access nested dictionary
            
        Returns:
            str: Translated text or concatenated keys with dots if translation not found
        """
        current = self._strings
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                # Return keys joined with dots if not found
                return '.'.join(keys)
        
        return current if isinstance(current, str) else '.'.join(keys)

def load_language(lang_code: str) -> LanguageStrings:
    """
    Load a language module and return its strings.
    Falls back to English if language is not supported.
    
    Args:
        lang_code: Language code to load
        
    Returns:
        LanguageStrings object containing the translations
    """
    if not lang_code:
        lang_code = DEFAULT_LANGUAGE
    
    lang_code = lang_code.lower()
    if lang_code not in SUPPORTED_LANGUAGES:
        debug_print(f"Language '{lang_code}' not supported, falling back to English")
        lang_code = DEFAULT_LANGUAGE
    
    try:
        module = importlib.import_module(f'languages.{lang_code}_lang')
        return LanguageStrings(module.LANG_STRINGS, name=lang_code)
    except ImportError:
        debug_print(f"Language module {lang_code} not found")
        if lang_code != DEFAULT_LANGUAGE:
            return load_language(DEFAULT_LANGUAGE)
        raise ImportError(f"Default language module {DEFAULT_LANGUAGE} not found!")
