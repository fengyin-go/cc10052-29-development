"""风险处置动作只读服务：支持处置数据按独立来源的通用查询、导出与回查。

处置动作由 ConclusionReviewService 在办理案件评审时按实际领用来源逐一生成，
这里仅提供资源路由所需的模块元数据与列表/详情能力。
"""
from __future__ import annotations

from app.services.base import BaseModuleService


class RiskActionService(BaseModuleService):
    MODULE = "risk_action"
    ENTITY = "风险处置动作"
    OPERATION_TERM = "处置"
    LIST_FIELDS = ["处置编号", "指标编码", "窗口标识", "来源标识", "事件编码", "处置类型", "处置时间"]
    REQUIRED_FIELDS: list[str] = []
    STATUS_ORDER = ["已处置", "待核实"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS: list[str] = []
