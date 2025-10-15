"""
模式管理 API 路由
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.models import LearnPatternRequest, LearnPatternResponse, PatternListResponse
from app.services.pattern_service import pattern_service
from app.routers.admin import get_current_user

router = APIRouter(prefix="/api/patterns", tags=["Pattern Management"])


@router.post("/learn", response_model=LearnPatternResponse)
async def learn_pattern(
    request: LearnPatternRequest,
    current_user: str = Depends(get_current_user)
):
    """
    學習新的驗證碼提取模式（需要管理員權限）
    
    管理員在後台粘貼郵件樣本，選中驗證碼後調用此 API
    """
    try:
        # 學習模式
        pattern = pattern_service.learn_from_highlight(
            email_content=request.email_content,
            highlighted_code=request.highlighted_code,
            position=request.highlight_position
        )
        
        return LearnPatternResponse(
            success=True,
            pattern_id=pattern.id,
            message="模式學習成功！",
            preview={
                "keywords_before": pattern.keywords_before,
                "keywords_after": pattern.keywords_after,
                "code_type": pattern.code_type,
                "code_length": pattern.code_length,
                "example": pattern.example_code
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"學習模式失敗: {str(e)}")


@router.get("", response_model=PatternListResponse)
async def list_patterns(current_user: str = Depends(get_current_user)):
    """
    列出所有已學習的模式（需要管理員權限）
    """
    try:
        patterns = pattern_service.get_all_patterns()
        
        patterns_data = [
            {
                "id": p.id,
                "keywords_before": p.keywords_before,
                "keywords_after": p.keywords_after,
                "code_type": p.code_type,
                "code_length": p.code_length,
                "example_code": p.example_code,
                "email_content": p.email_content,  # 包含完整邮件内容
                "confidence": p.confidence,
                "created_at": p.created_at.isoformat(),
                "usage_count": p.usage_count,
                "success_count": p.success_count,
                "success_rate": round(p.success_count / p.usage_count, 2) if p.usage_count > 0 else 0.0
            }
            for p in patterns
        ]
        
        return PatternListResponse(
            success=True,
            patterns=patterns_data,
            total=len(patterns_data)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取模式列表失敗: {str(e)}")


@router.delete("/{pattern_id}")
async def delete_pattern(
    pattern_id: str,
    current_user: str = Depends(get_current_user)
):
    """
    刪除指定模式（需要管理員權限）
    """
    try:
        success = pattern_service.delete_pattern(pattern_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="模式未找到")
        
        return {
            "success": True,
            "message": "模式已刪除"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刪除模式失敗: {str(e)}")


@router.get("/stats")
async def get_pattern_stats(current_user: str = Depends(get_current_user)):
    """
    獲取模式統計信息（需要管理員權限）
    """
    try:
        stats = pattern_service.get_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取統計信息失敗: {str(e)}")
