"""
FastAPI middleware for internationalization (i18n) support
"""

import re
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse
import logging

logger = logging.getLogger(__name__)

class I18nMiddleware(BaseHTTPMiddleware):
    """Middleware to handle language detection and routing"""

    def __init__(self, app, fallback_language: str = "en-US"):
        super().__init__(app)
        self.fallback_language = fallback_language
        self.supported_languages = ["en-US", "zh-CN"]
        self.language_patterns = {
            "en-US": re.compile(r"^/en/?"),
            "zh-CN": re.compile(r"^/zh-cn/?")
        }

        # Language cookie settings
        self.language_cookie_name = "tempmail_lang"
        self.cookie_max_age = 365 * 24 * 60 * 60  # 1 year

    async def dispatch(self, request: Request, call_next):
        """
        Process request and handle language detection

        Args:
            request: FastAPI request
            call_next: Next middleware in chain

        Returns:
            HTTP response
        """
        # Detect language
        detected_language = self._detect_language(request)

        # Store language in request state for use in endpoints
        request.state.language = detected_language

        # Handle language redirection
        if self._should_redirect(request, detected_language):
            redirect_response = self._redirect_with_language(request, detected_language)
            if redirect_response:
                return redirect_response

        # Process request
        response = await call_next(request)

        # Set language cookie
        self._set_language_cookie(response, detected_language)

        # Add language headers
        response.headers["Content-Language"] = detected_language

        return response

    def _detect_language(self, request: Request) -> str:
        """
        Detect language from various sources with priority

        Priority:
        1. URL path prefix (/en/, /zh-cn/)
        2. Query parameter (?lang=en)
        3. Cookie
        4. Accept-Language header
        5. Fallback language

        Args:
            request: FastAPI request

        Returns:
            Detected language code
        """
        # 1. Check URL path prefix
        path = str(request.url.path)
        for lang, pattern in self.language_patterns.items():
            if pattern.match(path):
                return lang

        # 2. Check query parameter
        lang_param = request.query_params.get("lang")
        if lang_param and lang_param in self.supported_languages:
            return lang_param

        # 3. Check cookie
        lang_cookie = request.cookies.get(self.language_cookie_name)
        if lang_cookie and lang_cookie in self.supported_languages:
            return lang_cookie

        # 4. Check Accept-Language header
        accept_language = request.headers.get("accept-language", "")
        if accept_language:
            # Parse Accept-Language header
            preferred_lang = self._parse_accept_language(accept_language)
            if preferred_lang:
                return preferred_lang

        # 5. Fallback language
        return self.fallback_language

    def _parse_accept_language(self, accept_language: str) -> Optional[str]:
        """
        Parse Accept-Language header and return best matching language

        Args:
            accept_language: Accept-Language header value

        Returns:
            Best matching language code or None
        """
        # Simple parsing - can be enhanced for quality values
        accept_language = accept_language.lower()

        # Check for exact matches
        if "zh-cn" in accept_language or "zh" in accept_language:
            return "zh-CN"
        if "en" in accept_language:
            return "en-US"

        return None

    def _should_redirect(self, request: Request, detected_language: str) -> bool:
        """
        Determine if request should be redirected to language-specific URL

        Args:
            request: FastAPI request
            detected_language: Detected language

        Returns:
            True if should redirect
        """
        path = str(request.url.path)
        query = str(request.url.query)

        # Don't redirect static files, API, admin, docs, or any special paths
        excluded_paths = [
            "/static/", "/api/", "/docs", "/redoc", "/admin",
            "/openapi.json", "/favicon.ico", "/test"
        ]

        for excluded in excluded_paths:
            if path.startswith(excluded):
                return False

        # Don't redirect if already has language prefix
        for pattern in self.language_patterns.values():
            if pattern.match(path):
                return False

        # Don't redirect root path if it's the default language
        if path == "/" and detected_language == self.fallback_language:
            return False

        # Additional safety: don't redirect if there are query parameters
        # that suggest this is an API call
        if query and any(param in query.lower() for param in ['request=', 'api=', 'token=']):
            return False

        return True

    def _redirect_with_language(self, request: Request, language: str) -> Response:
        """
        Redirect to language-specific URL

        Args:
            request: FastAPI request
            language: Target language

        Returns:
            Redirect response
        """
        path = str(request.url.path)
        query = str(request.url.query)

        # Safety check: don't redirect if already at target language
        for lang, pattern in self.language_patterns.items():
            if pattern.match(path) and lang == language:
                # Already at correct language, no redirect needed
                return None

        # Remove leading slash for clean URL construction
        clean_path = path.lstrip("/")

        # Remove existing language prefix if present
        for lang_prefix in ["en/", "zh-cn/"]:
            if clean_path.startswith(lang_prefix):
                clean_path = clean_path[len(lang_prefix):]
                break

        # Special handling: if path after language prefix is admin, redirect to /admin
        if clean_path.startswith("admin"):
            admin_path = f"/{clean_path}"

            # Add query parameters if exist (except 'lang')
            query_params = dict(request.query_params)
            query_params.pop("lang", None)

            if query_params:
                query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
                admin_path += f"?{query_string}"

            return RedirectResponse(
                url=admin_path,
                status_code=302,
                headers={"Set-Cookie": f"{self.language_cookie_name}={language}; Max-Age={self.cookie_max_age}; Path=/"}
            )

        # Construct new URL
        if clean_path == "" or clean_path == "/":
            if language == self.fallback_language:
                new_path = "/"
            else:
                new_path = f"/{language.lower()}/"
        else:
            if language == self.fallback_language:
                new_path = f"/{clean_path}"
            else:
                new_path = f"/{language.lower()}/{clean_path}"

        # Add query parameters if exist (except 'lang')
        query_params = dict(request.query_params)
        query_params.pop("lang", None)

        if query_params:
            query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
            new_path += f"?{query_string}"

        return RedirectResponse(
            url=new_path,
            status_code=302,
            headers={"Set-Cookie": f"{self.language_cookie_name}={language}; Max-Age={self.cookie_max_age}; Path=/"}
        )

    def _set_language_cookie(self, response: Response, language: str):
        """
        Set language preference cookie

        Args:
            response: HTTP response
            language: Language code
        """
        response.set_cookie(
            key=self.language_cookie_name,
            value=language,
            max_age=self.cookie_max_age,
            path="/",
            httponly=False,  # Allow JavaScript access
            samesite="lax"
        )

def get_language_from_request(request: Request) -> str:
    """
    Get language from request state

    Args:
        request: FastAPI request

    Returns:
        Language code
    """
    return getattr(request.state, "language", "en-US")