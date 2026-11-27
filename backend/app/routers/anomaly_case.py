"""异常案件工作台与案件评审的领域动作接口。

通用资源路由 /api/{module} 只承载标准增查与状态动作，案件归并、来源撤回、
校验单流转、评审领用/办理/复查等带业务判断的入口集中在这里，状态流转仍只
发生在 services 层，路由层不做业务判断。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.schemas import ActionResult
from app.services.anomaly_case import AnomalyCaseService
from app.services.anomaly_metric import AnomalyMetricService
from app.services.conclusion_review import ConclusionReviewService

router = APIRouter(prefix="/api", tags=["异常案件工作台"])

case_service = AnomalyCaseService()
review_service = ConclusionReviewService()
anomaly_service = AnomalyMetricService()


class LaunchFromAnomalyPayload(BaseModel):
    source_code: str
    event_code: str
    window_key: str = ""
    source_name: str = ""
    evidence: str = ""


class SourcePayload(BaseModel):
    source_code: str
    event_code: str
    source_name: str = ""
    evidence: str = ""


class WithdrawPayload(BaseModel):
    reason: str


class InvestigationPayload(BaseModel):
    investigation_type: str
    basis: str = ""


class NotePayload(BaseModel):
    note: str = ""


class HandleReviewPayload(BaseModel):
    decision: str
    remark: str = ""


def _wrap(result: dict[str, Any]) -> ActionResult:
    return ActionResult(
        ok=bool(result.get("ok")),
        message=str(result.get("message", "")),
        entry=result,
    )


# ---- 指标异常检测：从已确认异常日志发起异常调查 ----

@router.post("/anomaly_metric/{entry_id}/launch-investigation", response_model=ActionResult)
def launch_investigation(entry_id: int, payload: LaunchFromAnomalyPayload) -> ActionResult:
    result = anomaly_service.launch_investigation(
        entry_id=entry_id,
        source_code=payload.source_code,
        event_code=payload.event_code,
        window_key=payload.window_key,
        source_name=payload.source_name,
        evidence=payload.evidence,
    )
    return _wrap(result)


# ---- 案件工作台：案件与来源 ----

@router.get("/anomaly_case/metric/{metric_code}/overview")
def metric_case_overview(metric_code: str) -> dict[str, Any]:
    """单指标概览：新展示只列当前有效来源及可发起的调查类型。"""
    return case_service.metric_overview(metric_code)


@router.get("/anomaly_case/reviewable/queue")
def reviewable_queue() -> dict[str, Any]:
    """交付结论评审队列实际领用的可评审案件。"""
    items = case_service.reviewable_cases()
    return {"ok": True, "items": items, "total": len(items)}


@router.get("/anomaly_case/{case_id}/detail")
def case_detail(case_id: int) -> dict[str, Any]:
    detail = case_service.case_detail(case_id)
    if detail is None:
        return {"ok": False, "message": f"案件 {case_id} 不存在"}
    return {"ok": True, "case": detail}


@router.post("/anomaly_case/{case_id}/sources", response_model=ActionResult)
def submit_source(case_id: int, payload: SourcePayload) -> ActionResult:
    result = case_service.submit_source(
        case_id,
        payload.source_code,
        payload.event_code,
        source_name=payload.source_name,
        evidence=payload.evidence,
    )
    return _wrap(result)


@router.post("/anomaly_case/sources/{source_id}/withdraw", response_model=ActionResult)
def withdraw_source(source_id: int, payload: WithdrawPayload) -> ActionResult:
    return _wrap(case_service.withdraw_source(source_id, payload.reason))


# ---- 案件工作台：调查/校验单 ----

@router.post("/anomaly_case/{case_id}/investigations", response_model=ActionResult)
def create_investigation(case_id: int, payload: InvestigationPayload) -> ActionResult:
    return _wrap(
        case_service.create_investigation(
            case_id, payload.investigation_type, basis=payload.basis
        )
    )


@router.post("/anomaly_case/investigations/{investigation_id}/claim", response_model=ActionResult)
def claim_investigation(investigation_id: int) -> ActionResult:
    return _wrap(case_service.claim_investigation(investigation_id))


@router.post("/anomaly_case/investigations/{investigation_id}/verify-withdrawal", response_model=ActionResult)
def verify_withdrawal(investigation_id: int, payload: NotePayload) -> ActionResult:
    return _wrap(case_service.verify_withdrawal(investigation_id, payload.note))


@router.post("/anomaly_case/investigations/{investigation_id}/convert-single-source", response_model=ActionResult)
def convert_single_source(investigation_id: int, payload: NotePayload) -> ActionResult:
    return _wrap(case_service.convert_to_single_source(investigation_id, payload.note))


# ---- 结论评审队列：领取案件、办理、证据复查 ----

@router.post("/conclusion_review/cases/{case_id}/claim", response_model=ActionResult)
def claim_case(case_id: int) -> ActionResult:
    return _wrap(review_service.claim_case(case_id))


@router.post("/conclusion_review/{review_id}/handle-case", response_model=ActionResult)
def handle_case_review(review_id: int, payload: HandleReviewPayload) -> ActionResult:
    return _wrap(
        review_service.handle_case_review(review_id, payload.decision, payload.remark)
    )


@router.get("/conclusion_review/{review_id}/evidence")
def trace_review_evidence(review_id: int) -> dict[str, Any]:
    return review_service.trace_review_evidence(review_id)
