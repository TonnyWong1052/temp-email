"""
JWT 認證服務
處理 JWT token 的創建、驗證和用戶認證
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from app.config import settings

# 密碼哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """JWT 認證服務"""

    def __init__(self):
        self.secret_key = settings.admin_secret_key
        self.algorithm = settings.jwt_algorithm
        self.access_token_expire_minutes = settings.jwt_access_token_expire_minutes

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """驗證密碼"""
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """獲取密碼哈希"""
        return pwd_context.hash(password)

    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        創建 JWT access token
        
        Args:
            data: 要編碼的數據
            expires_delta: 自定義過期時間
            
        Returns:
            JWT token 字符串
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
            
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        驗證 JWT token
        
        Args:
            token: JWT token 字符串
            
        Returns:
            解碼後的 payload
            
        Raises:
            HTTPException: 如果 token 無效或過期
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="無效的認證憑證",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def authenticate_user(self, username: str, password: str) -> bool:
        """
        驗證用戶憑證
        
        Args:
            username: 用戶名
            password: 密碼
            
        Returns:
            認證是否成功
        """
        # 檢查用戶名和密碼是否與配置中的匹配
        # 注意：這裡使用明文密碼比較，因為當前系統中密碼是以明文存儲的
        # 在生產環境中，應該使用哈希密碼
        return username == settings.admin_username and password == settings.admin_password

    def create_user_token(self, username: str) -> str:
        """
        為用戶創建 JWT token
        
        Args:
            username: 用戶名
            
        Returns:
            JWT token 字符串
        """
        access_token_expires = timedelta(minutes=self.access_token_expire_minutes)
        access_token = self.create_access_token(
            data={"sub": username, "type": "access"}, expires_delta=access_token_expires
        )
        return access_token

    def get_current_user_from_token(self, token: str) -> str:
        """
        從 token 中獲取當前用戶名
        
        Args:
            token: JWT token 字符串
            
        Returns:
            用戶名
            
        Raises:
            HTTPException: 如果 token 無效或過期
        """
        payload = self.verify_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="無效的認證憑證",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return username


# 全局實例
auth_service = AuthService()