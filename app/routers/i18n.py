"""
i18n API Router
提供翻譯數據的 API 端點
"""

from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.i18n.translations import translation_manager

router = APIRouter(prefix="/api/i18n", tags=["i18n"])


@router.get("/translations")
async def get_translations(request: Request, lang: Optional[str] = None):
    """
    獲取當前語言的翻譯數據

    Args:
        lang: Optional language code (e.g., 'en-US', 'zh-CN')

    Returns:
        JSON response with translations
    """
    # 優先使用查詢參數，然後是 middleware 設置的語言，最後是默認值
    if lang and lang in translation_manager.supported_languages:
        current_language = lang
    else:
        current_language = getattr(request.state, "language", "en-US")

    # 獲取當前語言的翻譯
    translations = translation_manager.translations.get(current_language, {})

    # 將嵌套的字典轉換為扁平的點分隔鍵
    flat_translations = _flatten_dict(translations)

    return JSONResponse(
        content={
            "success": True,
            "data": {
                "language": current_language,
                "translations": flat_translations,
                "availableLanguages": translation_manager.get_available_languages()
            }
        }
    )


def _flatten_dict(d: dict, parent_key: str = '', sep: str = '.') -> dict:
    """
    將嵌套字典轉換為扁平字典，使用點分隔鍵

    Example:
        {"email": {"list": {"title": "My Emails"}}}
        -> {"email.list.title": "My Emails"}
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


@router.get("/languages")
async def get_available_languages():
    """
    獲取可用的語言列表

    Returns:
        JSON response with available languages
    """
    return JSONResponse(
        content={
            "success": True,
            "data": {
                "languages": translation_manager.get_available_languages()
            }
        }
    )
