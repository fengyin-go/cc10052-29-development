"""异常证据来源只读服务：支持来源明细的通用查询与导出。

来源的登记、撤回等业务流转统一在 AnomalyCaseService 内完成，这里仅提供
资源路由所需的模块元数据与列表/详情能力，保证证据表可被独立核对与导出。
"""
from __future__ import annotations

from app.services.base import BaseModuleService


class AnomalySourceService(BaseModuleService):
    MODULE = "anomaly_source"
    ENTITY = "异常证据来源"
    OPERATION_TERM = "上报"
    LIST_FIELDS = ["来源编号", "来源标识", "来源名称", "事件编码", "有效性", "上报次数", "撤回原因"]
    REQUIRED_FIELDS: list[str] = []
    STATUS_ORDER = ["有效", "已撤回"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS: list[str] = []
