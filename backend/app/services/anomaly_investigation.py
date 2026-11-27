"""异常调查/校验单只读服务：支持校验单的通用查询与导出。

申请、领取、冲突识别与两条办理出路统一在 AnomalyCaseService 内完成，
这里仅提供资源路由所需的模块元数据与列表/详情能力。
"""
from __future__ import annotations

from app.services.base import BaseModuleService


class AnomalyInvestigationService(BaseModuleService):
    MODULE = "anomaly_investigation"
    ENTITY = "异常校验单"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["校验单编号", "案件编号", "指标编码", "窗口标识", "调查类型", "校验单状态", "办理出路"]
    REQUIRED_FIELDS: list[str] = []
    STATUS_ORDER = ["已申请", "已领取", "已办理"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS: list[str] = []
