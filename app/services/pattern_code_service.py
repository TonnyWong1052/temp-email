"""
基於用戶訓練模式的驗證碼提取服務
"""

import re
from typing import List
from app.models import Code
from app.services.pattern_service import pattern_service


class PatternCodeService:
    """基於模式的驗證碼提取服務"""
    
    def __init__(self):
        self.pattern_service = pattern_service
    
    def extract_codes(self, text: str) -> List[Code]:
        """
        使用已學習的模式提取驗證碼
        
        Args:
            text: 郵件文本內容
        
        Returns:
            List[Code]: 提取到的驗證碼列表
        """
        codes = []
        patterns = self.pattern_service.get_all_patterns()
        
        if not patterns:
            # 如果沒有訓練的模式，返回空列表
            return codes
        
        # 遍歷所有已學習的模式
        for pattern in patterns:
            # 嘗試使用前置關鍵詞匹配
            for keyword in pattern.keywords_before:
                if keyword.lower() in text.lower():
                    # 找到關鍵詞位置（不區分大小寫）
                    keyword_pattern = re.escape(keyword)
                    match = re.search(keyword_pattern, text, re.IGNORECASE)
                    
                    if match:
                        # 從關鍵詞後開始搜索驗證碼
                        search_start = match.end()
                        search_text = text[search_start:search_start + 100]
                        
                        # 使用模式的正則表達式匹配驗證碼（不區分大小寫）
                        code_match = re.search(pattern.regex, search_text, re.IGNORECASE)
                        
                        if code_match:
                            extracted_code = code_match.group().strip()
                            
                            # 檢查是否已經提取過這個驗證碼
                            if not self._is_duplicate(codes, extracted_code):
                                codes.append(Code(
                                    code=extracted_code,
                                    type=pattern.code_type,
                                    length=len(extracted_code),
                                    pattern=f"user_pattern_{pattern.id}",
                                    confidence=pattern.confidence
                                ))
                                
                                # 記錄模式使用
                                self.pattern_service.increment_usage(pattern.id, success=True)
                                
                                # 找到一個就跳出內層循環
                                break
        
        # 按置信度排序
        return sorted(codes, key=lambda x: x.confidence, reverse=True)
    
    def extract_from_html(self, html: str) -> List[Code]:
        """從 HTML 中提取驗證碼"""
        # 移除 HTML 標籤
        text = re.sub(r"<[^>]*>", " ", html)
        # 解碼 HTML 實體
        text = self._decode_html_entities(text)
        return self.extract_codes(text)
    
    def _is_duplicate(self, codes: List[Code], code: str) -> bool:
        """檢查是否重複"""
        return any(c.code == code for c in codes)
    
    def _decode_html_entities(self, text: str) -> str:
        """解碼 HTML 實體"""
        import html
        return html.unescape(text)


# 單例
pattern_code_service = PatternCodeService()
