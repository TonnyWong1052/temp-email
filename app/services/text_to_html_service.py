"""
纯文本转 HTML 服务 - 自动识别 URL 和图片链接

将纯文本邮件中的 URL 自动转换为可点击的链接
将图片 URL 自动转换为 <img> 标签
"""

import re
from typing import Optional
from html import escape


class TextToHtmlService:
    """纯文本转 HTML 转换器"""

    # 圖片文件擴展名
    IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.ico'
    }

    def convert_text_to_html(self, text: str) -> str:
        """
        将纯文本转换为 HTML，自动识别：
        - URL 转换为可点击链接
        - 图片 URL 转换为 <img> 标签
        - 保留换行和空白

        Args:
            text: 纯文本内容

        Returns:
            HTML 格式内容
        """
        if not text:
            return ""

        # 步驟 0: 統一換行符 (處理 \r\n, \r, \n)
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # 步驟 1: 先處理 Markdown 風格的連結 <url> 和圖片 [url] (在 escape 之前)
        text = self._convert_markdown_style_links(text)

        # 步驟 2: 將換行符轉換為特殊標記 (避免被 escape 影響)
        text = text.replace('\n', '{{NEWLINE}}')

        # 步驟 3: 轉義 HTML 特殊字符（保護原始文本）
        html = escape(text)

        # 步驟 4: 替換換行標記為 <br>
        html = html.replace('{{NEWLINE}}', '<br>')

        # 步驟 5: 替換 URL 佔位符 (在 escape 之後、識別其他 URL 之前)
        html = self._replace_url_placeholders(html)

        # 步驟 6: 識別並轉換剩餘的 URL (處理 escape 後的文本, 排除已經是 HTML 標籤的部分)
        html = self._convert_urls_to_links(html)

        # 步驟 7: 包裝在 <div> 中，添加樣式保留空白和自動換行
        html = f'<div style="white-space: pre-wrap; word-wrap: break-word;">{html}</div>'

        return html

    def _convert_markdown_style_links(self, text: str) -> str:
        """
        转换 Markdown 风格的链接 (在 escape 之前处理)

        支持格式:
        - <url>: 尖括号包裹的 URL
        - [url]: 方括号包裹的图片 URL

        Args:
            text: 原始纯文本

        Returns:
            替换后的文本 (使用 Unicode 占位符，避免被 escape 干扰)
        """
        import uuid

        # 儲存 URL 映射 (使用實例變量臨時存儲)
        if not hasattr(self, '_temp_url_map'):
            self._temp_url_map = {}

        # 处理 <url> 格式 (如 <https://aka.ms/GetOutlookForMac>)
        def replace_angle_bracket_url(match):
            url = match.group(1)
            placeholder = f"__URLPLACEHOLDER_{uuid.uuid4().hex[:8]}__"

            # 存儲 URL 和類型
            self._temp_url_map[placeholder] = {
                'url': url,
                'is_image': self._is_image_url(url)
            }

            return placeholder

        # 匹配 <url> 格式
        text = re.sub(r'<(https?://[^>]+)>', replace_angle_bracket_url, text)

        # 處理 [url] 格式 (如 [https://example.com/image.jpg])
        def replace_bracket_url(match):
            url = match.group(1)

            # 只處理圖片 URL
            if self._is_image_url(url):
                placeholder = f"__URLPLACEHOLDER_{uuid.uuid4().hex[:8]}__"
                self._temp_url_map[placeholder] = {
                    'url': url,
                    'is_image': True
                }
                return placeholder
            else:
                # 非圖片 URL 保持原樣
                return f'[{url}]'

        # 匹配 [url] 格式
        text = re.sub(r'\[(https?://[^\]]+)\]', replace_bracket_url, text)

        return text

    def _replace_url_placeholders(self, text: str) -> str:
        """
        替换 URL 占位符为实际的 HTML 标签

        使用特殊标记避免后续 URL 匹配干扰

        Args:
            text: 包含占位符的文本 (已被 escape)

        Returns:
            替换后的 HTML
        """
        if not hasattr(self, '_temp_url_map') or not self._temp_url_map:
            return text

        # 第一階段：替換為帶有保護標記的 HTML
        for placeholder, data in self._temp_url_map.items():
            url = data['url']
            is_image = data['is_image']

            if is_image:
                # 转换为图片标签（添加保护标记）
                replacement = f'{{{{PROTECTED}}}}<br><img src="{url}" alt="邮件图片" class="mail-content-image" loading="lazy" style="max-width: 100%; height: auto;"><br>{{{{/PROTECTED}}}}'
            else:
                # 转换为链接（添加保护标记）
                replacement = f'{{{{PROTECTED}}}}<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>{{{{/PROTECTED}}}}'

            text = text.replace(placeholder, replacement)

        # 清空映射
        self._temp_url_map = {}

        return text

    def _convert_urls_to_links(self, text: str) -> str:
        """
        将文本中的 URL 转换为可点击链接或图片

        注意: 跳过已经在 HTML 标签中的 URL 和受保护区域

        支持：
        - http:// 和 https:// URL
        - 常见图片格式自动转换为 <img>
        - Markdown 格式的图片 [描述](url)
        """
        # 步驟 1: 分離受保護區域
        protected_sections = []
        protected_pattern = r'\{\{PROTECTED\}\}(.*?)\{\{/PROTECTED\}\}'

        def save_protected(match):
            index = len(protected_sections)
            protected_sections.append(match.group(1))
            return f'__PROTECTED_{index}__'

        text = re.sub(protected_pattern, save_protected, text, flags=re.DOTALL)

        # 步驟 2: 匹配普通 URL（已被 escape 的字符）
        # 使用負向先行斷言，跳過已經在 HTML 屬性中的 URL
        url_pattern = r'(?<!href=")(?<!src=")https?://[^\s<>&\'"]+[^\s<>&\'".,;:!?)]'

        def replace_url(match):
            url = match.group(0)

            # 检查是否为图片 URL
            if self._is_image_url(url):
                # 转换为图片标签
                return f'<br><img src="{url}" alt="邮件图片" class="mail-content-image" loading="lazy" style="max-width: 100%; height: auto;"><br>'
            else:
                # 转换为链接
                return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'

        # 替換所有 URL
        result = re.sub(url_pattern, replace_url, text)

        # 步驟 3: 還原受保護區域
        for index, content in enumerate(protected_sections):
            result = result.replace(f'__PROTECTED_{index}__', content)

        # 步驟 4: 處理 Markdown 格式的圖片: [alt](url) 或 ![alt](url)
        result = self._convert_markdown_images(result)

        return result

    def _is_image_url(self, url: str) -> bool:
        """
        判断 URL 是否为图片

        检查方式：
        1. 文件扩展名
        2. 常见图片 CDN 域名
        """
        url_lower = url.lower()

        # 檢查文件擴展名
        for ext in self.IMAGE_EXTENSIONS:
            if ext in url_lower:
                return True

        # 檢查常見圖片 CDN 或路徑關鍵字
        image_keywords = [
            '/images/', '/img/', '/image/', '/picture/', '/photo/',
            'imgur.com', 'cloudinary.com', 'imgix.net'
        ]

        for keyword in image_keywords:
            if keyword in url_lower:
                return True

        return False

    def _convert_markdown_images(self, text: str) -> str:
        """
        转换 Markdown 格式的图片: [alt](url) 或 ![alt](url)

        例如: [image](https://example.com/image.jpg)
        """
        # 匹配 ![alt](url) 或 [alt](url) 格式
        pattern = r'!?\[([^\]]*)\]\(([^)]+)\)'

        def replace_markdown(match):
            alt_text = match.group(1) or '邮件图片'
            url = match.group(2)

            if self._is_image_url(url):
                return f'<br><img src="{url}" alt="{escape(alt_text)}" class="mail-content-image" loading="lazy" style="max-width: 100%; height: auto;"><br>'
            else:
                # 如果不是圖片，轉換為普通連結
                return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{escape(alt_text) if alt_text else url}</a>'

        return re.sub(pattern, replace_markdown, text)

    def enhance_html_content(self, text_content: str, html_content: Optional[str]) -> str:
        """
        增强邮件内容显示

        Args:
            text_content: 纯文本内容
            html_content: HTML 内容（可能为 None）

        Returns:
            增强后的 HTML 内容
        """
        if html_content:
            # 如果有 HTML 內容，直接返回（已由 html_sanitizer 清理）
            return html_content
        else:
            # 如果沒有 HTML 內容，將純文本轉換為 HTML
            return self.convert_text_to_html(text_content)


# 單例
text_to_html_service = TextToHtmlService()
