"""
Translation loader and manager for FastAPI i18n support
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class TranslationManager:
    """Manage translations for different languages"""

    def __init__(self, translations_dir: Optional[str] = None):
        """
        Initialize translation manager

        Args:
            translations_dir: Directory containing translation files
        """
        if translations_dir is None:
            translations_dir = Path(__file__).parent / "locales"

        self.translations_dir = Path(translations_dir)
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.fallback_language = "en-US"
        self.supported_languages = ["en-US", "zh-CN"]

        self._load_all_translations()

    def _load_all_translations(self):
        """Load all translation files"""
        for lang in self.supported_languages:
            self._load_language(lang)

    def _load_language(self, language: str):
        """
        Load translations for a specific language

        Args:
            language: Language code (e.g., 'en-US', 'zh-CN')
        """
        translation_file = self.translations_dir / f"{language}.json"

        try:
            if translation_file.exists():
                with open(translation_file, 'r', encoding='utf-8') as f:
                    self.translations[language] = json.load(f)
                logger.info(f"Loaded translations for {language}")
            else:
                logger.warning(f"Translation file not found: {translation_file}")
                self.translations[language] = {}
        except Exception as e:
            logger.error(f"Error loading translations for {language}: {e}")
            self.translations[language] = {}

    def get_translation(self, key: str, language: Optional[str] = None, **kwargs) -> str:
        """
        Get translation for a key

        Args:
            key: Translation key (e.g., 'common.buttons.generate')
            language: Target language
            **kwargs: Variables for string formatting

        Returns:
            Translated string
        """
        if language is None:
            language = self.fallback_language

        # Try to get translation for the specified language
        translation = self._get_nested_value(
            self.translations.get(language, {}),
            key
        )

        # Fallback to default language if translation not found
        if translation is None and language != self.fallback_language:
            translation = self._get_nested_value(
                self.translations.get(self.fallback_language, {}),
                key
            )

        # Return key if no translation found
        if translation is None:
            logger.warning(f"Translation not found for key: {key}")
            return key

        # Format with kwargs if provided
        try:
            if kwargs:
                return translation.format(**kwargs)
            return translation
        except (KeyError, ValueError) as e:
            logger.error(f"Error formatting translation '{key}': {e}")
            return translation

    def _get_nested_value(self, data: Dict[str, Any], key: str) -> Optional[str]:
        """
        Get nested value from dictionary using dot notation

        Args:
            data: Dictionary to search
            key: Dot-separated key (e.g., 'common.buttons.generate')

        Returns:
            Found value or None
        """
        keys = key.split('.')
        current = data

        try:
            for k in keys:
                current = current[k]
            return current if isinstance(current, str) else None
        except (KeyError, TypeError):
            return None

    def reload_translations(self):
        """Reload all translation files"""
        self.translations.clear()
        self._load_all_translations()

    def get_available_languages(self) -> Dict[str, str]:
        """
        Get available languages with their display names

        Returns:
            Dictionary of language_code -> display_name
        """
        return {
            "en-US": "English",
            "zh-CN": "简体中文"
        }

# Global translation manager instance
translation_manager = TranslationManager()

def t(key: str, language: Optional[str] = None, **kwargs) -> str:
    """
    Shortcut function to get translation

    Args:
        key: Translation key
        language: Target language
        **kwargs: Variables for string formatting

    Returns:
        Translated string
    """
    return translation_manager.get_translation(key, language, **kwargs)