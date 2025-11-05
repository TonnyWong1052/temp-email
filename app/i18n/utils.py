"""
Utility functions for i18n support
"""

from typing import Dict, Any, Optional
from fastapi import Request
from .translations import translation_manager

def get_translations_for_frontend(language: str) -> Dict[str, Any]:
    """
    Get translations formatted for frontend consumption

    Args:
        language: Target language code

    Returns:
        Dictionary of translations for frontend
    """
    # Get all translations for the language
    translations = translation_manager.translations.get(language, {})

    # Flatten nested structure for easier frontend usage
    flattened = {}

    def flatten_dict(d: Dict[str, Any], prefix: str = ""):
        """Recursively flatten dictionary"""
        for key, value in d.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flatten_dict(value, new_key)
            else:
                flattened[new_key] = value

    flatten_dict(translations)

    return {
        "language": language,
        "translations": flattened,
        "availableLanguages": translation_manager.get_available_languages()
    }

def get_language_display_name(language_code: str) -> str:
    """
    Get display name for language code

    Args:
        language_code: Language code (e.g., 'en-US')

    Returns:
        Display name (e.g., 'English')
    """
    available_languages = translation_manager.get_available_languages()
    return available_languages.get(language_code, language_code)

def is_language_supported(language_code: str) -> bool:
    """
    Check if language is supported

    Args:
        language_code: Language code to check

    Returns:
        True if supported, False otherwise
    """
    return language_code in translation_manager.supported_languages

def get_current_language(request: Request) -> str:
    """
    Get current language from request

    Args:
        request: FastAPI request

    Returns:
        Current language code
    """
    # 安全地获取语言，如果沒有設置則返回預設語言
    return getattr(request.state, "language", "en-US")


def safe_get_current_language(request: Request) -> str:
    """
    Safely get current language from request with fallback detection

    Args:
        request: FastAPI request

    Returns:
        Current language code
    """
    try:
        # 嘗試從 request.state 獲取
        language = getattr(request.state, "language", None)
        if language:
            return language
        
        # 如果沒有設置，嘗試從路徑檢測
        path = str(request.url.path)
        if path.startswith("/zh-cn/"):
            return "zh-CN"
        if path.startswith("/en/"):
            return "en-US"
        
        # 檢查查詢參數
        lang_param = request.query_params.get("lang")
        if lang_param and lang_param in ["en-US", "zh-CN"]:
            return lang_param
        
        # 檢查 Cookie
        lang_cookie = request.cookies.get("tempmail_lang")
        if lang_cookie and lang_cookie in ["en-US", "zh-CN"]:
            return lang_cookie
        
        # 檢查 Accept-Language 標頭
        accept_language = request.headers.get("accept-language", "")
        if "zh-cn" in accept_language.lower() or "zh" in accept_language.lower():
            return "zh-CN"
        
        # 預設英文
        return "en-US"
    except Exception:
        return "en-US"

def create_language_switcher_links(request: Request) -> Dict[str, str]:
    """
    Create language switcher links for current page

    Args:
        request: FastAPI request

    Returns:
        Dictionary of language_code -> switch_url
    """
    try:
        current_path = str(request.url.path)
        current_query = str(request.url.query)

        # Remove existing language prefix from path
        for lang_prefix in ["/en/", "/zh-cn/"]:
            if current_path.startswith(lang_prefix):
                current_path = current_path[len(lang_prefix):]
                if not current_path.startswith("/"):
                    current_path = "/" + current_path
                break

        # Ensure path starts with /
        if not current_path.startswith("/"):
            current_path = "/" + current_path

        # Build switch URLs
        switch_urls = {}
        for lang in ["en-US", "zh-CN"]:
            if lang == "en-US" and current_path == "/":
                # For English, root path is sufficient
                switch_url = "/"
            else:
                # Add language prefix
                path_without_leading_slash = current_path.lstrip("/")
                if path_without_leading_slash == "":
                    switch_url = f"/{lang.lower()}/"
                else:
                    switch_url = f"/{lang.lower()}/{path_without_leading_slash}"

            # Add query parameters except 'lang'
            if current_query and "lang=" not in current_query:
                switch_url += f"?{current_query}"

            switch_urls[lang] = switch_url

        return switch_urls
    except Exception:
        # Fallback URLs
        return {
            "en-US": "/",
            "zh-CN": "/zh-cn/"
        }

def validate_language_code(language_code: str) -> Optional[str]:
    """
    Validate and normalize language code

    Args:
        language_code: Input language code

    Returns:
        Normalized language code or None if invalid
    """
    if not language_code:
        return None

    # Normalize to uppercase
    normalized = language_code.upper()

    # Handle common variations
    language_mapping = {
        "EN": "en-US",
        "ZH": "zh-CN",
        "ZH-CN": "zh-CN",
        "ZH_CN": "zh-CN"
    }

    normalized = language_mapping.get(normalized, normalized)

    # Check if supported
    if normalized in translation_manager.supported_languages:
        return normalized

    return None