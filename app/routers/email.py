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

        # 回傳同時包含 email 與 address 欄位，確保向後相容
        return {
            "success": True,
            "data": {
                "email": email.address,
                "address": email.address,  # 向後相容：部分工具/測試使用 address 欄位
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
    获取邮件列表（完整內容版本）

    🆕 自動返回完整郵件內容：
    - **content**: 完整純文字內容（經過清理）
    - **htmlContent**: 完整 HTML 內容（經過清理和增強）
    - 自動從 Cloudflare KV 批量獲取完整內容（如需要）

    - **token**: 邮箱token
    - **limit**: 最大返回数量 (1-100，建議保持默認值控制響應大小)
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

    # 🆕 批量獲取 KV 郵件的完整內容（如果需要）
    use_kv = should_use_cloudflare_kv(email.address)
    if use_kv and unique_mails:
        # 檢查是否有郵件缺少完整內容
        incomplete_mails = [m for m in unique_mails if not m.html_content]

        if incomplete_mails:
            if debug:
                print(f"[Email Router] Found {len(incomplete_mails)} mails with incomplete content, fetching from KV")

            try:
                from app.services.kv_mail_service import kv_client

                # 批量獲取完整內容
                full_mails = await kv_client.fetch_mails(email.address, fetch_full_content=True)

                # 建立 ID 到完整郵件的映射
                full_mail_map = {m.id: m for m in full_mails}

                # 更新不完整的郵件
                for mail in unique_mails:
                    if mail.id in full_mail_map and not mail.html_content:
                        full_mail = full_mail_map[mail.id]
                        mail.content = full_mail.content
                        mail.html_content = full_mail.html_content
                        mail.to = full_mail.to or mail.to

                        if debug:
                            print(f"[Email Router] Updated mail {mail.id} with full content")

            except Exception as e:
                if debug:
                    print(f"[Email Router] Error fetching full content from KV: {e}")
                    import traceback
                    print(traceback.format_exc())
                # 獲取失敗時不拋出錯誤，繼續使用現有內容

    # 🆕 構建回應：返回完整內容和增強的 HTML
    # 1. 如果有 HTML 內容 → 清理後返回
    # 2. 如果只有純文本 → 自動轉換為 HTML（識別 URL 和圖片）
    def _build_mail_response(m):
        # 處理內容和 HTML
        if m.html_content:
            # 有 HTML 內容，清理後返回
            sanitized_html = html_sanitizer.sanitize(m.html_content)
            # 同步提供更乾淨的純文字內容（由 HTML 提取）
            try:
                safe_text_content = mail_service._extract_text_from_html(sanitized_html or m.html_content)
            except Exception:
                safe_text_content = m.content or ""
        else:
            # 只有純文本，轉換為 HTML（自動識別 URL 和圖片）
            sanitized_html = text_to_html_service.convert_text_to_html(m.content)
            safe_text_content = m.content or ""

        return {
            "id": m.id,
            "from": m.from_,
            "to": m.to,
            "subject": m.subject,
            "content": safe_text_content,  # 完整純文字內容
            "htmlContent": sanitized_html,  # 完整 HTML 內容
            "receivedAt": m.received_at.isoformat(),
            "read": m.read,
            "hasCode": bool(m.codes),
        }

    return {
        "success": True,
        "data": {
            "email": email.address,
            "total": len(storage_service.get_mails(token)),
            "mails": [_build_mail_response(mail) for mail in unique_mails],
        },
    }


@router.get("/{token}/mails/{mail_id}")
async def get_mail_detail(token: str, mail_id: str):
    """
    获取单封邮件详情

    - **token**: 邮箱token
    - **mail_id**: 邮件ID
    """
    from app.config import settings
    debug = bool(getattr(settings, "debug_email_fetch", False))

    email = storage_service.get_email_by_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="邮箱未找到")

    mail = storage_service.get_mail_by_id(token, mail_id)
    if not mail:
        raise HTTPException(status_code=404, detail="邮件未找到")

    # 檢查是否需要從 Cloudflare KV 獲取完整內容
    # 條件：1) 郵件來自 Cloudflare KV  2) html_content 為空
    use_kv = should_use_cloudflare_kv(email.address)
    needs_full_content = use_kv and not mail.html_content

    if needs_full_content:
        if debug:
            print(f"[Email Router] Mail {mail_id} has incomplete content, fetching full content from KV")

        # 從 KV 獲取完整郵件內容
        try:
            from app.services.kv_mail_service import kv_client

            # 使用 fetch_full_content=True 獲取完整內容
            full_mails = await kv_client.fetch_mails(email.address, fetch_full_content=True)

            # 查找匹配的郵件
            full_mail = next((m for m in full_mails if m.id == mail_id), None)

            if full_mail:
                if debug:
                    print(f"[Email Router] Found full mail content: content_len={len(full_mail.content) if full_mail.content else 0}, has_html={bool(full_mail.html_content)}")

                # 更新 Storage 中的郵件對象
                mail.content = full_mail.content
                mail.html_content = full_mail.html_content
                mail.to = full_mail.to or mail.to  # 確保 to 字段不為空

                if debug:
                    print(f"[Email Router] Updated mail in storage with full content")
            else:
                if debug:
                    print(f"[Email Router] Warning: Could not find mail {mail_id} in full content fetch")

        except Exception as e:
            if debug:
                print(f"[Email Router] Error fetching full content: {e}")
                import traceback
                print(traceback.format_exc())
            # 獲取失敗時不拋出錯誤，繼續使用現有內容

    # 标记为已读
    storage_service.mark_as_read(token, mail_id)

    # 增強內容顯示：
    # 1. 如果有 HTML 內容 → 清理後返回
    # 2. 如果只有純文本 → 自動轉換為 HTML（識別 URL 和圖片）
    if mail.html_content:
        # 有 HTML 內容，清理後返回
        sanitized_html = html_sanitizer.sanitize(mail.html_content)
        # 同步提供更乾淨的純文字內容（由 HTML 提取），避免 text/plain 版本可能的重複段落
        try:
            safe_text_content = mail_service._extract_text_from_html(sanitized_html or mail.html_content)
        except Exception:
            safe_text_content = mail.content or ""
    else:
        # 只有純文本，轉換為 HTML（自動識別 URL 和圖片）
        sanitized_html = text_to_html_service.convert_text_to_html(mail.content)
        safe_text_content = mail.content or ""

    return {
        "success": True,
        "data": {
            "id": mail.id,
            "from": mail.from_,
            "to": mail.to,
            "subject": mail.subject,
            # 返回優化後的純文字內容（若 HTML 存在則以 HTML 提取的純文字為準，否則使用原始 text/plain）
            "content": safe_text_content,
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
    token: str,
    timeout: int = Query(30, ge=1, le=300),
    since: Optional[str] = None,
    auto_extract_code: bool = Query(False, description="是否自動提取驗證碼"),
    extraction_method: str = Query("smart", description="提取方法: smart/pattern/llm/regex"),
    min_confidence: float = Query(0.8, ge=0.0, le=1.0, description="最小置信度"),
):
    """
    等待新邮件 (长轮询)

    - **token**: 邮箱token
    - **timeout**: 超时时间(秒) (1-300)
    - **since**: 时间戳，只返回此时间后的邮件
    - **auto_extract_code**: 是否自動提取驗證碼（默認 false，保持向後兼容）
    - **extraction_method**: 提取方法
      - 'smart': 智能級聯（Pattern → LLM → Regex）
      - 'pattern': 只使用用戶訓練的模式
      - 'llm': 只使用 LLM 提取
      - 'regex': 只使用正則表達式
    - **min_confidence**: 最小置信度過濾（0.0-1.0）
    """
    email = storage_service.get_email_by_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="邮箱未找到")

    since_date = datetime.fromisoformat(since) if since else datetime.now()

    # 根據 auto_extract_code 參數選擇是否自動提取
    if auto_extract_code:
        # 使用增強版本（帶驗證碼提取）
        new_mails, extraction_stats = await mail_service.wait_for_new_mail_with_codes(
            email.address, since_date, timeout, extraction_method, min_confidence
        )

        if new_mails:
            storage_service.save_mails(token, new_mails)

            # 構建郵件預覽
            def _build_mail_preview(mail):
                preview = {
                    "id": mail.id,
                    "from": mail.from_,
                    "subject": mail.subject,
                    "content": mail.content[:200] if mail.content else "",
                    "receivedAt": mail.received_at.isoformat(),
                    "hasCode": bool(mail.codes),
                }

                # 添加驗證碼信息
                if mail.codes:
                    preview["codes"] = [
                        {
                            "code": code.code,
                            "type": code.type,
                            "length": code.length,
                            "confidence": code.confidence,
                            "pattern": code.pattern,
                            "method": extraction_stats.get("source"),
                        }
                        for code in mail.codes
                    ]

                return preview

            return {
                "success": True,
                "data": {
                    "hasNew": True,
                    "count": len(new_mails),
                    "mails": [_build_mail_preview(mail) for mail in new_mails],
                    "extractionStats": extraction_stats,
                },
            }
    else:
        # 使用原始版本（不提取驗證碼，保持向後兼容）
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
                            "content": mail.content[:200] if mail.content else "",
                            "receivedAt": mail.received_at.isoformat(),
                            "hasCode": bool(mail.codes),
                            "code": mail.codes[0].code if mail.codes else None,
                        }
                        for mail in new_mails
                    ],
                },
            }

    raise HTTPException(status_code=408, detail="在超时时间内没有新邮件")


@router.get("/{token}/wait-code")
async def wait_for_code(
    token: str,
    timeout: int = Query(30, ge=1, le=300),
    since: Optional[str] = None,
    extraction_method: str = Query("smart", description="提取方法: smart/pattern/llm/regex"),
    min_confidence: float = Query(0.8, ge=0.0, le=1.0, description="最小置信度"),
):
    """
    等待新郵件並返回驗證碼（快速 API）

    專注於驗證碼場景，返回第一個找到的高置信度驗證碼

    - **token**: 邮箱token
    - **timeout**: 超时时间(秒) (1-300)
    - **since**: 时间戳，只返回此时间后的邮件
    - **extraction_method**: 提取方法 (smart/pattern/llm/regex)
    - **min_confidence**: 最小置信度（0.0-1.0）

    返回：
    - **code**: 驗證碼
    - **type**: 類型 (numeric/alphanumeric/token)
    - **confidence**: 置信度
    - **mailId**: 郵件 ID
    - **from**: 寄件人
    - **subject**: 主題
    - **extractedAt**: 提取時間
    - **extractionMethod**: 實際使用的提取方法
    - **timeMs**: 提取耗時（毫秒）
    """
    email = storage_service.get_email_by_token(token)
    if not email:
        raise HTTPException(status_code=404, detail="邮箱未找到")

    since_date = datetime.fromisoformat(since) if since else datetime.now()

    # 使用增強版本等待新郵件並提取驗證碼
    new_mails, extraction_stats = await mail_service.wait_for_new_mail_with_codes(
        email.address, since_date, timeout, extraction_method, min_confidence
    )

    if new_mails:
        storage_service.save_mails(token, new_mails)

        # 查找第一個包含高置信度驗證碼的郵件
        for mail in new_mails:
            if mail.codes:
                # 按置信度排序，取最高的
                sorted_codes = sorted(mail.codes, key=lambda c: c.confidence, reverse=True)
                best_code = sorted_codes[0]

                return {
                    "success": True,
                    "data": {
                        "code": best_code.code,
                        "type": best_code.type,
                        "confidence": best_code.confidence,
                        "length": best_code.length,
                        "mailId": mail.id,
                        "from": mail.from_,
                        "subject": mail.subject,
                        "extractedAt": datetime.now().isoformat(),
                        "extractionMethod": extraction_stats.get("source"),
                        "timeMs": extraction_stats.get("timeMs"),
                    },
                }

        # 有新郵件但沒有找到驗證碼
        raise HTTPException(
            status_code=404,
            detail=f"收到 {len(new_mails)} 封新郵件，但未找到符合條件的驗證碼（置信度 >= {min_confidence}）",
        )

    # 超時，無新郵件
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
