from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from app.models import EmailGenerateResponse, MailListResponse, CodeResponse
from app.services.email_service import email_service
from app.services.mail_service import mail_service
from app.services.storage_service import storage_service
from app.services.html_sanitizer import html_sanitizer
from app.services.text_to_html_service import text_to_html_service
from app.config import settings, should_use_cloudflare_kv

router = APIRouter(prefix="/api/email", tags=["Email"])


@router.api_route("/generate", methods=["POST", "GET"], response_model=EmailGenerateResponse)
async def generate_email(
    prefix: Optional[str] = Query(None, description="自定义前缀 (可选)"),
    domain: Optional[str] = Query(None, description="指定域名 (可选，必须在可用域名列表中)")
):
    """
    生成临时邮箱

    - **prefix**: 自定义前缀 (可选)
    - **domain**: 指定域名 (可选，必须在可用域名列表中)
    """
    try:
        email = email_service.generate_email(prefix, domain)
        storage_service.save_email(email)

        return {
            "success": True,
            "data": {
                "email": email.address,
                "token": email.token,
                "createdAt": email.created_at.isoformat(),
                "expiresAt": email.expires_at.isoformat(),
                "createdAtMs": int(email.created_at.timestamp() * 1000),
                "expiresAtMs": int(email.expires_at.timestamp() * 1000),
                "webUrl": email_service.get_email_web_url(email.address),
                "useCloudflareKV": should_use_cloudflare_kv(email.address),
            },
        }
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"无效的域名: {str(e)}. 使用 /api/domains 获取可用域名列表。",
        )


@router.get("/{token}/mails", response_model=MailListResponse)
async def get_mails(
    token: str,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
):
    """
    获取邮件列表

    - **token**: 邮箱token
    - **limit**: 最大返回数量 (1-100)
    - **offset**: 偏移量
    - **unread_only**: 只返回未读邮件
    """
    from app.config import settings
    debug = bool(getattr(settings, "debug_email_fetch", False))

    if debug:
        print(f"[Email Router] GET /api/email/{token}/mails - limit={limit}, offset={offset}, unread_only={unread_only}")

    email = storage_service.get_email_by_token(token)
    if not email:
        if debug:
            print(f"[Email Router] ❌ Email not found for token: {token}")
        raise HTTPException(status_code=404, detail="邮箱未找到")

    if debug:
        print(f"[Email Router] ✓ Found email: {email.address}")

    # 先从API获取最新邮件
    if debug:
        print(f"[Email Router] Fetching mails from API for: {email.address}")

    fresh_mails = await mail_service.fetch_mails(email.address)

    if debug:
        print(f"[Email Router] API returned {len(fresh_mails)} mails")

    if fresh_mails:
        if debug:
            print(f"[Email Router] Saving {len(fresh_mails)} mails to storage")
        storage_service.save_mails(token, fresh_mails)

    # 获取邮件
    if unread_only:
        mails = storage_service.get_unread_mails(token)
        mails = mails[offset : offset + limit]
        if debug:
            print(f"[Email Router] Returning {len(mails)} unread mails (after pagination)")
    else:
        mails = storage_service.get_mails(token, limit, offset)
        if debug:
            print(f"[Email Router] Returning {len(mails)} mails (after pagination)")

    # API响应层去重 - 使用Set确保每个ID只出现一次
    seen_ids = set()
    unique_mails = []
    for mail in mails:
        if mail.id not in seen_ids:
            unique_mails.append(mail)
            seen_ids.add(mail.id)

    return {
        "success": True,
        "data": {
            "email": email.address,
            "total": len(storage_service.get_mails(token)),
            "mails": [
                {
                    "id": mail.id,
                    "from": mail.from_,
                    "subject": mail.subject,
                    "content": mail.content[:200],  # 摘要
                    "receivedAt": mail.received_at.isoformat(),
                    "read": mail.read,
                    "hasCode": bool(mail.codes),
                }
                for mail in unique_mails
            ],
        },
    }


@router.get("/{token}/mails/{mail_id}")
async def get_mail_detail(token: str, mail_id: str):
    """
    获取单封邮件详情

    - **token**: 邮箱token
    - **mail_id**: 邮件ID
    """
    email = storage_service.get_email_by_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="邮箱未找到")

    mail = storage_service.get_mail_by_id(token, mail_id)
    if not mail:
        raise HTTPException(status_code=404, detail="邮件未找到")

    # 标记为已读
    storage_service.mark_as_read(token, mail_id)

    # 增強內容顯示：
    # 1. 如果有 HTML 內容 → 清理後返回
    # 2. 如果只有純文本 → 自動轉換為 HTML（識別 URL 和圖片）
    if mail.html_content:
        # 有 HTML 內容，清理後返回
        sanitized_html = html_sanitizer.sanitize(mail.html_content)
    else:
        # 只有純文本，轉換為 HTML（自動識別 URL 和圖片）
        sanitized_html = text_to_html_service.convert_text_to_html(mail.content)

    return {
        "success": True,
        "data": {
            "id": mail.id,
            "from": mail.from_,
            "to": mail.to,
            "subject": mail.subject,
            "content": mail.content,
            "htmlContent": sanitized_html,  # 返回增強後的 HTML
            "receivedAt": mail.received_at.isoformat(),
            "read": mail.read,
        },
    }


@router.get("/{token}/codes", response_model=CodeResponse)
async def get_codes(
    token: str,
    mail_id: Optional[str] = None,
    method: Optional[str] = Query(None, description="提取方法: 'llm' 或 'pattern'")
):
    """
    提取验证码（按需提取，不自动提取）

    - **token**: 邮箱token
    - **mail_id**: 指定邮件ID (可选)
    - **method**: 提取方法 (可选)
      - 'llm': 使用 LLM 智能提取
      - 'pattern': 使用模式匹配提取（基於用戶訓練）
      - 如果未指定，使用配置中的默認方法
    """
    # 使用配置中的默認提取方法
    if method is None:
        method = settings.default_code_extraction_method

    email = storage_service.get_email_by_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="邮箱未找到")

    if mail_id:
        # 从指定邮件提取
        mail = storage_service.get_mail_by_id(token, mail_id)
        if not mail:
            raise HTTPException(status_code=404, detail="邮件未找到")
        mails = [mail]
    else:
        # 从所有邮件提取
        mails = storage_service.get_mails(token)

    # 根據 method 參數選擇提取方法
    if method == "pattern":
        # 使用模式匹配提取
        from app.services.pattern_code_service import pattern_code_service
        
        for mail in mails:
            codes = pattern_code_service.extract_codes(mail.content)
            if not codes and mail.html_content:
                codes = pattern_code_service.extract_from_html(mail.html_content)
            mail.codes = codes
        
        mails_to_extract = mails
    else:
        # 使用 LLM 或正則表達式提取（默認）
        mails_to_extract = await mail_service._extract_codes_for_mails(mails)

    codes = []
    for mail in mails_to_extract:
        if mail.codes:
            for code in mail.codes:
                codes.append(
                    {
                        "code": code.code,
                        "type": code.type,
                        "length": code.length,
                        "confidence": code.confidence,
                        "pattern": code.pattern,
                        "mailId": mail.id,
                        "from": mail.from_,
                        "subject": mail.subject,
                        "extractedAt": datetime.now().isoformat(),
                        "method": method
                    }
                )

    return {"success": True, "data": {"codes": codes, "method": method}}


@router.get("/{token}/wait")
async def wait_for_new_mail(
    token: str, timeout: int = Query(30, ge=1, le=120), since: Optional[str] = None
):
    """
    等待新邮件 (长轮询)

    - **token**: 邮箱token
    - **timeout**: 超时时间(秒) (1-120)
    - **since**: 时间戳，只返回此时间后的邮件
    """
    email = storage_service.get_email_by_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="邮箱未找到")

    since_date = datetime.fromisoformat(since) if since else datetime.now()

    new_mails = await mail_service.wait_for_new_mail(email.address, since_date, timeout)

    if new_mails:
        storage_service.save_mails(token, new_mails)
        return {
            "success": True,
            "data": {
                "hasNew": True,
                "count": len(new_mails),
                "mails": [
                    {
                        "id": mail.id,
                        "from": mail.from_,
                        "subject": mail.subject,
                        "content": mail.content[:200],
                        "receivedAt": mail.received_at.isoformat(),
                        "hasCode": bool(mail.codes),
                        "code": mail.codes[0].code if mail.codes else None,
                    }
                    for mail in new_mails
                ],
            },
        }

    raise HTTPException(status_code=408, detail="在超时时间内没有新邮件")


@router.delete("/{token}")
async def delete_email(token: str):
    """
    删除邮箱

    - **token**: 邮箱token
    """
    success = storage_service.delete_email(token)
    if not success:
        raise HTTPException(status_code=404, detail="邮箱未找到")

    return {"success": True, "message": "邮箱删除成功"}
