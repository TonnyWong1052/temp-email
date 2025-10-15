"""
HTML 清理服務 - 安全地清理郵件 HTML 內容

提供白名單標籤和屬性過濾，防止 XSS 攻擊
支援連結、圖片、格式化文本等安全元素
"""

import re
from typing import Optional
from html import escape, unescape


class HtmlSanitizer:
    """HTML 清理器 - 使用白名單方式清理 HTML"""

    # 允許的標籤（白名單）
    ALLOWED_TAGS = {
        # 連結
        "a",
        # 圖片
        "img",
        # 格式化
        "p", "br", "strong", "b", "em", "i", "u", "s", "del", "ins",
        "code", "pre", "blockquote", "hr",
        # 標題
        "h1", "h2", "h3", "h4", "h5", "h6",
        # 列表
        "ul", "ol", "li",
        # 表格
        "table", "thead", "tbody", "tr", "td", "th",
        # 區塊
        "div", "span",
    }

    # 允許的屬性（按標籤分類）
    ALLOWED_ATTRIBUTES = {
        "a": ["href", "title", "rel", "target"],
        "img": ["src", "alt", "title", "width", "height"],
        "td": ["colspan", "rowspan"],
        "th": ["colspan", "rowspan"],
        "*": ["class", "id"],  # 全局屬性
    }

    # 危險標籤（必須移除）
    DANGEROUS_TAGS = {
        "script", "style", "iframe", "frame", "frameset",
        "object", "embed", "applet", "link", "meta", "base"
    }

    # 危險屬性模式（事件處理器）
    DANGEROUS_ATTR_PATTERN = re.compile(r'^on\w+', re.IGNORECASE)

    def sanitize(self, html: Optional[str]) -> Optional[str]:
        """
        清理 HTML 內容

        Args:
            html: 原始 HTML 內容

        Returns:
            清理後的安全 HTML，如果輸入為 None 則返回 None
        """
        if not html:
            return None

        try:
            # 步驟 1: 移除危險標籤
            html = self._remove_dangerous_tags(html)

            # 步驟 2: 移除危險屬性（事件處理器）
            html = self._remove_dangerous_attributes(html)

            # 步驟 3: 過濾標籤（白名單）
            html = self._filter_tags(html)

            # 步驟 4: 處理連結（自動添加安全屬性）
            html = self._secure_links(html)

            # 步驟 5: 處理圖片（添加樣式類）
            html = self._process_images(html)

            return html

        except Exception as e:
            # 如果清理失敗，返回純文本
            print(f"[HTML Sanitizer] Error sanitizing HTML: {e}")
            return self._strip_all_tags(html)

    def _remove_dangerous_tags(self, html: str) -> str:
        """移除危險標籤（script, style, iframe 等）"""
        for tag in self.DANGEROUS_TAGS:
            # 移除開始和結束標籤及其內容
            pattern = rf'<{tag}[^>]*>.*?</{tag}>'
            html = re.sub(pattern, '', html, flags=re.DOTALL | re.IGNORECASE)
            # 移除自閉合標籤
            pattern = rf'<{tag}[^>]*/?>'
            html = re.sub(pattern, '', html, flags=re.IGNORECASE)
        return html

    def _remove_dangerous_attributes(self, html: str) -> str:
        """移除危險屬性（on* 事件處理器）"""
        # 匹配標籤中的 on* 屬性
        pattern = r'<([a-zA-Z][a-zA-Z0-9]*)\s+([^>]*?)>'

        def clean_attrs(match):
            tag_name = match.group(1)
            attrs = match.group(2)

            # 移除 on* 屬性
            attrs = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', attrs, flags=re.IGNORECASE)
            attrs = re.sub(r'\s+on\w+\s*=\s*[^\s>]+', '', attrs, flags=re.IGNORECASE)

            return f'<{tag_name} {attrs}>'.replace('  ', ' ').replace('< ', '<')

        return re.sub(pattern, clean_attrs, html)

    def _filter_tags(self, html: str) -> str:
        """
        過濾標籤（白名單）

        注意：這是簡化實現，生產環境建議使用 bleach 庫
        """
        # 移除不在白名單中的標籤
        def replace_tag(match):
            tag_name = match.group(1).lower()
            is_closing = match.group(2) == '/'
            full_tag = match.group(0)

            if tag_name in self.ALLOWED_TAGS:
                return full_tag
            else:
                # 移除標籤，保留內容
                return ''

        # 匹配開始標籤和結束標籤
        pattern = r'<(/?)([a-zA-Z][a-zA-Z0-9]*)[^>]*?>'
        return re.sub(pattern, replace_tag, html)

    def _secure_links(self, html: str) -> str:
        """
        處理連結，自動添加安全屬性

        - target="_blank" (在新標籤頁打開)
        - rel="noopener noreferrer" (防止 window.opener 攻擊)
        """
        pattern = r'<a\s+([^>]*?)>'

        def add_security_attrs(match):
            attrs = match.group(1)

            # 檢查是否已有 target
            if 'target=' not in attrs.lower():
                attrs += ' target="_blank"'

            # 檢查是否已有 rel
            if 'rel=' not in attrs.lower():
                attrs += ' rel="noopener noreferrer"'
            else:
                # 如果已有 rel，確保包含 noopener noreferrer
                attrs = re.sub(
                    r'rel\s*=\s*["\']([^"\']*)["\']',
                    lambda m: f'rel="{m.group(1)} noopener noreferrer"',
                    attrs
                )

            return f'<a {attrs}>'.replace('  ', ' ')

        return re.sub(pattern, add_security_attrs, html, flags=re.IGNORECASE)

    def _process_images(self, html: str) -> str:
        """
        處理圖片，添加樣式類和 loading="lazy"
        """
        pattern = r'<img\s+([^>]*?)>'

        def add_img_attrs(match):
            attrs = match.group(1)

            # 添加 loading="lazy" (延遲加載)
            if 'loading=' not in attrs.lower():
                attrs += ' loading="lazy"'

            # 添加 class (用於 CSS 樣式)
            if 'class=' not in attrs.lower():
                attrs += ' class="mail-content-image"'
            else:
                # 如果已有 class，追加 mail-content-image
                attrs = re.sub(
                    r'class\s*=\s*["\']([^"\']*)["\']',
                    lambda m: f'class="{m.group(1)} mail-content-image"',
                    attrs
                )

            return f'<img {attrs}>'.replace('  ', ' ')

        return re.sub(pattern, add_img_attrs, html, flags=re.IGNORECASE)

    def _strip_all_tags(self, html: str) -> str:
        """
        移除所有 HTML 標籤，返回純文本

        用於清理失敗時的回退方案
        """
        # 移除所有標籤
        text = re.sub(r'<[^>]+>', '', html)

        # 解碼 HTML 實體
        text = unescape(text)

        # 清理多餘空白
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        return text

    def get_text_preview(self, html: Optional[str], max_length: int = 200) -> str:
        """
        從 HTML 中提取純文本預覽

        Args:
            html: HTML 內容
            max_length: 最大長度

        Returns:
            純文本預覽（截斷）
        """
        if not html:
            return ""

        # 移除所有標籤
        text = self._strip_all_tags(html)

        # 截斷
        if len(text) > max_length:
            text = text[:max_length] + '...'

        return text


# 單例
html_sanitizer = HtmlSanitizer()
