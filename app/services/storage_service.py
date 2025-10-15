from datetime import datetime
from typing import Dict, List, Optional
from app.models import Email, Mail


class StorageService:
    """內存存儲服務"""

    def __init__(self):
        self.emails: Dict[str, Email] = {}  # token -> Email
        self.mails: Dict[str, List[Mail]] = {}  # emailToken -> List[Mail]
        self.email_by_address: Dict[str, str] = {}  # address -> token

    # ===== 郵箱操作 =====

    def save_email(self, email: Email) -> None:
        """保存郵箱"""
        self.emails[email.token] = email
        self.email_by_address[email.address] = email.token

    def get_email_by_token(self, token: str) -> Optional[Email]:
        """根據token獲取郵箱"""
        return self.emails.get(token)

    def get_email_by_address(self, address: str) -> Optional[Email]:
        """根據地址獲取郵箱"""
        token = self.email_by_address.get(address)
        if not token:
            return None
        return self.get_email_by_token(token)

    def delete_email(self, token: str) -> bool:
        """刪除郵箱"""
        email = self.emails.get(token)
        if not email:
            return False

        del self.emails[token]
        del self.email_by_address[email.address]
        if token in self.mails:
            del self.mails[token]
        return True

    def get_all_emails(self) -> List[Email]:
        """獲取所有郵箱"""
        return list(self.emails.values())

    # ===== 郵件操作 =====

    def save_mails(self, email_token: str, mails: List[Mail]) -> None:
        """保存郵件"""
        from app.config import settings
        debug = bool(getattr(settings, "debug_email_fetch", False))

        if debug:
            print(f"[Storage Service] save_mails() called for token: {email_token}")
            print(f"[Storage Service] Incoming mails count: {len(mails)}")

        # 為每封郵件設置emailToken
        for mail in mails:
            mail.email_token = email_token

        existing_mails = self.mails.get(email_token, [])
        if debug:
            print(f"[Storage Service] Existing mails count: {len(existing_mails)}")
        existing_ids = {m.id for m in existing_mails}

        # 合併郵件，避免重複
        merged_mails = existing_mails.copy()
        new_count = 0
        for new_mail in mails:
            if new_mail.id not in existing_ids:
                merged_mails.append(new_mail)
                existing_ids.add(new_mail.id)
                new_count += 1
                if debug:
                    print(f"[Storage Service]   ✓ Added new mail: id={new_mail.id}, from={new_mail.from_}")
            else:
                if debug:
                    print(f"[Storage Service]   ⊘ Skipped duplicate mail: id={new_mail.id}")

        if debug:
            print(f"[Storage Service] Added {new_count} new mails, Total now: {len(merged_mails)}")

        self.mails[email_token] = merged_mails

        # 更新郵件數量
        email = self.emails.get(email_token)
        if email:
            email.mail_count = len(merged_mails)
            if debug:
                print(f"[Storage Service] Updated email.mail_count to {email.mail_count}")

    def get_mails(
        self, email_token: str, limit: Optional[int] = None, offset: int = 0
    ) -> List[Mail]:
        """獲取郵件列表"""
        from app.config import settings
        debug = bool(getattr(settings, "debug_email_fetch", False))

        mails = self.mails.get(email_token, [])

        if debug:
            print(f"[Storage Service] get_mails() for token: {email_token}")
            print(f"[Storage Service]   Total stored mails: {len(mails)}")

        # 按接收時間倒序排序
        sorted_mails = sorted(mails, key=lambda m: m.received_at, reverse=True)

        if limit is not None:
            result = sorted_mails[offset : offset + limit]
            if debug:
                print(f"[Storage Service]   Returning {len(result)} mails (limit={limit}, offset={offset})")
            return result

        result = sorted_mails[offset:]
        if debug:
            print(f"[Storage Service]   Returning {len(result)} mails (offset={offset})")
        return result

    def get_mail_by_id(self, email_token: str, mail_id: str) -> Optional[Mail]:
        """獲取單封郵件"""
        mails = self.mails.get(email_token, [])
        return next((m for m in mails if m.id == mail_id), None)

    def mark_as_read(self, email_token: str, mail_id: str) -> bool:
        """標記郵件為已讀"""
        mail = self.get_mail_by_id(email_token, mail_id)
        if not mail:
            return False
        mail.read = True
        return True

    def get_unread_mails(self, email_token: str) -> List[Mail]:
        """獲取未讀郵件"""
        mails = self.mails.get(email_token, [])
        return [m for m in mails if not m.read]

    # ===== 清理和統計 =====

    def cleanup_expired(self) -> int:
        """清理過期郵箱"""
        count = 0
        now = datetime.now()

        tokens_to_delete = [
            token for token, email in self.emails.items() if email.expires_at < now
        ]

        for token in tokens_to_delete:
            self.delete_email(token)
            count += 1

        return count

    def get_stats(self) -> dict:
        """獲取統計信息"""
        total_emails = len(self.emails)
        total_mails = sum(len(mails) for mails in self.mails.values())

        return {
            "total_emails": total_emails,
            "total_mails": total_mails,
            "active_emails": total_emails,
        }


# 單例
storage_service = StorageService()
