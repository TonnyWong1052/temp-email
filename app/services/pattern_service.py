"""
模式管理服務
負責學習、保存、加載用戶訓練的驗證碼提取模式
"""

import json
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from app.models import Pattern


class PatternService:
    """模式管理服務"""
    
    def __init__(self):
        self.patterns_file = Path("data/patterns.json")
        self.patterns: List[Pattern] = []
        self._ensure_data_directory()
        self._load_patterns()
    
    def _ensure_data_directory(self):
        """確保 data 目錄存在"""
        self.patterns_file.parent.mkdir(exist_ok=True)
        if not self.patterns_file.exists():
            self.patterns_file.write_text("[]", encoding="utf-8")
    
    def _load_patterns(self):
        """從文件加載模式"""
        try:
            data = json.loads(self.patterns_file.read_text(encoding="utf-8"))
            self.patterns = [Pattern(**p) for p in data]
        except Exception as e:
            print(f"[Pattern Service] Failed to load patterns: {e}")
            self.patterns = []
    
    def _save_patterns(self):
        """保存模式到文件"""
        try:
            data = [p.model_dump(mode='json') for p in self.patterns]
            self.patterns_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[Pattern Service] Failed to save patterns: {e}")
    
    def learn_from_highlight(
        self, 
        email_content: str, 
        highlighted_code: str, 
        position: int
    ) -> Pattern:
        """
        從用戶高亮學習新模式
        
        只保留最新的一個模式，創建新模式時自動刪除所有舊模式
        
        Args:
            email_content: 完整郵件內容
            highlighted_code: 用戶選中的驗證碼
            position: 驗證碼在郵件中的位置
        
        Returns:
            Pattern: 學習到的模式
        """
        # 提取上下文（前後各30個字符）
        context_before = email_content[max(0, position - 30):position]
        context_after = email_content[
            position + len(highlighted_code):
            position + len(highlighted_code) + 30
        ]
        
        # 提取關鍵詞
        keywords_before = self._extract_keywords(context_before)
        keywords_after = self._extract_keywords(context_after[:20])
        
        # 判斷驗證碼類型
        if highlighted_code.isdigit():
            code_type = "numeric"
            regex = f"\\d{{{len(highlighted_code)}}}"
        elif highlighted_code.isalnum():
            code_type = "alphanumeric"
            regex = f"[A-Za-z0-9]{{{len(highlighted_code)}}}"
        else:
            code_type = "token"
            regex = f"[A-Za-z0-9_-]{{{len(highlighted_code)}}}"
        
        # 創建新模式
        pattern = Pattern(
            id=f"pattern_{secrets.token_hex(4)}",
            keywords_before=keywords_before,
            keywords_after=keywords_after,
            code_type=code_type,
            code_length=len(highlighted_code),
            regex=regex,
            example_code=highlighted_code,
            email_content=email_content,  # 保存完整邮件内容
            confidence=0.85,
            created_at=datetime.now(),
            usage_count=0,
            success_count=0
        )
        
        # 只保留最新模式，刪除所有舊模式
        self.patterns = [pattern]
        self._save_patterns()
        
        return pattern
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        從上下文提取關鍵詞
        
        識別距離驗證碼最近的關鍵詞，支持多語言
        """
        # 清理文本
        text = text.strip()
        
        keywords = []
        
        # 常見驗證碼關鍵詞模式
        keyword_patterns = [
            r'驗證碼[是：:\s]*',
            r'验证码[是：:\s]*',
            r'動態碼[是：:\s]*',
            r'动态码[是：:\s]*',
            r'verification\s+code[:\s]*',
            r'code[:\s]*',
            r'OTP[:\s]*',
            r'otp[:\s]*',
            r'your\s+code[:\s]*',
            r'code\s+is[:\s]*',
        ]
        
        # 查找匹配的關鍵詞
        for pattern in keyword_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                clean_keyword = match.strip()
                if clean_keyword and clean_keyword not in keywords:
                    keywords.append(clean_keyword)
        
        # 如果沒找到關鍵詞，嘗試提取最後15個字符作為上下文
        if not keywords and len(text) > 0:
            # 提取最後的詞組
            last_part = text[-15:].strip()
            if last_part:
                keywords.append(last_part)
        
        return keywords
    
    def get_all_patterns(self) -> List[Pattern]:
        """獲取所有模式"""
        return self.patterns
    
    def get_pattern_by_id(self, pattern_id: str) -> Optional[Pattern]:
        """根據 ID 獲取模式"""
        return next((p for p in self.patterns if p.id == pattern_id), None)
    
    def delete_pattern(self, pattern_id: str) -> bool:
        """刪除模式"""
        pattern = self.get_pattern_by_id(pattern_id)
        if pattern:
            self.patterns.remove(pattern)
            self._save_patterns()
            return True
        return False
    
    def increment_usage(self, pattern_id: str, success: bool = True):
        """增加模式使用次數"""
        pattern = self.get_pattern_by_id(pattern_id)
        if pattern:
            pattern.usage_count += 1
            if success:
                pattern.success_count += 1
            self._save_patterns()
    
    def get_stats(self) -> dict:
        """獲取統計信息"""
        total_patterns = len(self.patterns)
        total_usage = sum(p.usage_count for p in self.patterns)
        
        return {
            "total_patterns": total_patterns,
            "total_usage": total_usage,
            "patterns_with_usage": len([p for p in self.patterns if p.usage_count > 0])
        }


# 單例
pattern_service = PatternService()
