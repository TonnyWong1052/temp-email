"""
.env 檔案讀寫服務
支援安全的環境變數配置管理
"""

import os
from typing import Dict, Optional, Any
from pathlib import Path
import re


class EnvService:
    """環境變數配置服務"""

    def __init__(self, env_path: str = ".env"):
        self.env_path = Path(env_path)

    def read_env(self) -> Dict[str, str]:
        """
        讀取 .env 檔案內容
        返回 key-value 字典
        """
        if not self.env_path.exists():
            return {}

        env_dict = {}
        try:
            with open(self.env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    # 跳過空行和註釋
                    if not line or line.startswith("#"):
                        continue

                    # 解析 KEY=VALUE 格式
                    match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', line)
                    if match:
                        key, value = match.groups()
                        # 移除引號
                        value = value.strip()
                        if (value.startswith('"') and value.endswith('"')) or \
                           (value.startswith("'") and value.endswith("'")):
                            value = value[1:-1]
                        env_dict[key] = value

        except Exception as e:
            print(f"讀取 .env 檔案失敗: {e}")
            return {}

        return env_dict

    def write_env(self, config: Dict[str, Any], preserve_comments: bool = True) -> bool:
        """
        寫入配置到 .env 檔案

        Args:
            config: 配置字典
            preserve_comments: 是否保留註釋和空行

        Returns:
            bool: 是否成功
        """
        try:
            # 讀取現有內容（保留註釋）
            existing_lines = []
            existing_keys = set()

            if preserve_comments and self.env_path.exists():
                with open(self.env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        # 保留註釋和空行
                        if not stripped or stripped.startswith("#"):
                            existing_lines.append(line)
                        else:
                            # 檢查是否為 KEY=VALUE
                            match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=', stripped)
                            if match:
                                key = match.group(1)
                                existing_keys.add(key)
                                # 如果 config 中有這個 key，使用新值
                                if key in config:
                                    value = self._format_value(config[key])
                                    existing_lines.append(f"{key}={value}\n")
                                else:
                                    # 保留原始行
                                    existing_lines.append(line)
                            else:
                                existing_lines.append(line)

            # 添加新的配置項
            new_lines = []
            for key, value in config.items():
                if key not in existing_keys:
                    formatted_value = self._format_value(value)
                    new_lines.append(f"{key}={formatted_value}\n")

            # 寫入檔案
            with open(self.env_path, "w", encoding="utf-8") as f:
                f.writelines(existing_lines)
                if new_lines:
                    f.write("\n# Auto-generated settings\n")
                    f.writelines(new_lines)

            return True

        except Exception as e:
            print(f"寫入 .env 檔案失敗: {e}")
            return False

    def update_env(self, updates: Dict[str, Any]) -> bool:
        """
        更新特定的環境變數
        保留其他配置不變

        Args:
            updates: 要更新的配置項

        Returns:
            bool: 是否成功
        """
        current = self.read_env()
        current.update(updates)
        return self.write_env(current, preserve_comments=True)

    def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """獲取單個配置值"""
        env_dict = self.read_env()
        return env_dict.get(key, default)

    def _format_value(self, value: Any) -> str:
        """
        格式化配置值
        處理特殊字符和類型轉換
        """
        if value is None:
            return ""

        # 轉換為字符串
        str_value = str(value)

        # 布爾值特殊處理
        if isinstance(value, bool):
            str_value = "true" if value else "false"

        # 如果包含空格或特殊字符，添加引號
        if " " in str_value or "#" in str_value or any(c in str_value for c in "\"'$"):
            # 轉義內部引號
            str_value = str_value.replace('"', '\\"')
            return f'"{str_value}"'

        return str_value

    def backup_env(self) -> bool:
        """創建 .env 備份"""
        if not self.env_path.exists():
            return False

        try:
            backup_path = self.env_path.with_suffix(".env.backup")
            import shutil
            shutil.copy2(self.env_path, backup_path)
            return True
        except Exception as e:
            print(f"備份失敗: {e}")
            return False

    def validate_config(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        驗證配置的有效性

        Returns:
            (is_valid, error_message)
        """
        # 基本驗證規則
        required_keys = []  # 可以定義必需的 key

        for key in required_keys:
            if key not in config:
                return False, f"缺少必需配置: {key}"

        # 驗證 key 格式
        for key in config.keys():
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
                return False, f"無效的配置 key: {key}"

        return True, None


# 全局實例
env_service = EnvService()
