"""
FastAPI i18n module for internationalization support
"""

from .middleware import I18nMiddleware, get_language_from_request
from .translations import translation_manager, t
from .utils import (
    get_translations_for_frontend,
    get_language_display_name,
    is_language_supported,
    get_current_language,
    create_language_switcher_links,
    validate_language_code
)

__all__ = [
    "I18nMiddleware",
    "get_language_from_request",
    "translation_manager",
    "t",
    "get_translations_for_frontend",
    "get_language_display_name",
    "is_language_supported",
    "get_current_language",
    "create_language_switcher_links",
    "validate_language_code"
]