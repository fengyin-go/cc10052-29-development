"""业务路由汇总：案件工作台等领域动作路由先注册，通用资源路由兜底。"""
from __future__ import annotations

from app.routers import anomaly_case, resource

# anomaly_case 含 /api/{module}/... 的定制动作，需在通用资源路由前注册，
# 避免动态路径抢先匹配；通用路由自身只匹配标准资源路径。
ROUTERS = [anomaly_case, resource]
