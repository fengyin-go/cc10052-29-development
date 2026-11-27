"""指标异常检测领域服务：管理指标值异常波动的基线对比、异常评分与误报标记。

数据链路位置：质量检测层，消费指标计算结果与时效监控告警，检测指标异常波动，
把确认异常推送给结论评审队列进入人工处置。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class AnomalyMetricService(BaseModuleService):
    MODULE = "anomaly_metric"
    ENTITY = "异常事件"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["异常编号", "指标编码", "基线区间", "观测值", "异常评分"]
    REQUIRED_FIELDS = ["异常编号", "指标编码", "基线区间"]
    STATUS_ORDER = ["待确认", "已确认", "误报"]
    ACTION_RULES = {"确认异常": "已确认", "标记误报": "误报"}
    NEGATIVE_ACTIONS = []

    # ---- 业务扩展：异常检测与人工处置 ----

    def confirm_anomaly(self, entry_id: int) -> dict[str, Any]:
        """确认异常并把处置单推送到结论评审队列。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待确认":
            return {"ok": False, "message": "仅待确认异常可确认"}
        entry["status"] = "已确认"
        entry["pending"] = False
        entry["确认时间"] = datetime.now(timezone.utc).isoformat()
        review_rows = store.rows("conclusion_review")
        review_rows.append({
            "id": max((int(r.get("id", 0)) for r in review_rows), default=0) + 1,
            "记录编号": f"RV-AN-{entry_id}",
            "实验编码": str(entry.get("指标编码", "")).replace("M-", "EXP_-"),
            "评审结论": f"指标异常 {entry.get('异常编号', '')} 待评审处置",
            "评审角色": "数据质量",
            "评审时间": datetime.now(timezone.utc).isoformat(),
            "status": "待评审",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": f"异常 {entry.get('异常编号')} 已确认并进入评审"}

    def mark_false_positive(self, entry_id: int, reason: str) -> dict[str, Any]:
        """标记误报并把原因写回数据时效监控修正告警。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待确认":
            return {"ok": False, "message": "仅待确认异常可标记误报"}
        if not reason.strip():
            return {"ok": False, "message": "标记误报必须填写原因"}
        entry["status"] = "误报"
        entry["pending"] = False
        entry["abnormal"] = True
        entry["误报原因"] = reason
        source = str(entry.get("异常编号", ""))
        if source.startswith("AN-DF-"):
            target_id = source.replace("AN-DF-", "").split("-")[0]
            if target_id.isdigit():
                fresh = store.find("data_freshness", int(target_id))
                if fresh is not None:
                    fresh["status"] = "新鲜"
                    fresh["时效等级"] = "新鲜"
                    fresh["pending"] = False
        return {"ok": True, "message": f"已标记误报（{reason}），来源告警已修正"}

    def detect_deviation(self, metric_code: str, observed: float, baseline: float) -> dict[str, Any]:
        """对比观测值与基线，偏差超阈值时登记新异常事件。"""
        if not metric_code:
            return {"ok": False, "message": "指标编码为空"}
        if baseline == 0:
            deviation = abs(observed)
        else:
            deviation = abs(observed - baseline) / abs(baseline)
        if deviation < 0.2:
            return {"ok": True, "message": f"偏差 {deviation:.2%} 未超阈值", "anomaly": False}
        rows = store.rows(self.MODULE)
        rows.append({
            "id": max((int(r.get("id", 0)) for r in rows), default=0) + 1,
            "异常编号": f"AN-DV-{metric_code}-{datetime.now(timezone.utc).timestamp():.0f}",
            "指标编码": metric_code,
            "基线区间": f"[{baseline}, {baseline}]",
            "观测值": str(observed),
            "异常评分": str(round(min(deviation, 1.0), 2)),
            "status": "待确认",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": f"偏差 {deviation:.2%} 超阈值，异常已登记", "anomaly": True}

    def batch_confirm(self) -> dict[str, Any]:
        """批量确认全部高分待确认异常。"""
        pending = [
            r for r in store.rows(self.MODULE)
            if r.get("status") == "待确认" and float(str(r.get("异常评分", "0")) or 0) >= 0.7
        ]
        done = sum(1 for r in pending if self.confirm_anomaly(int(r.get("id", 0))).get("ok"))
        return {"ok": True, "message": f"高分异常批量确认 {done} 条"}

    def consume_from_metric_compute(self, metric_code: str) -> list[float]:
        """读取指标计算层最近作业产出，构造观测值序列。"""
        values = []
        for r in store.rows("metric_compute"):
            if r.get("指标编码") == metric_code and r.get("status") == "已完成":
                value = str(r.get("作业名称", "")).split("-")[-1]
                if value.replace(".", "").isdigit():
                    values.append(float(value))
        return values

    def consume_from_metric_catalog(self, metric_code: str) -> dict[str, Any]:
        """读取指标口径中心的口径版本，锁定异常检测的口径上下文。"""
        metric = next((m for m in store.rows("metric_catalog") if m.get("指标编码") == metric_code), None)
        if metric is None:
            return {"ok": False, "message": "口径不存在"}
        return {"ok": True, "口径版本": metric.get("口径版本", ""), "聚合窗口": metric.get("聚合窗口", "")}

    def export_confirmed(self, metric_code: str) -> list[dict[str, Any]]:
        """导出已确认异常清单，供报告生成器写入风险附注。"""
        return [
            {
                "异常编号": r.get("异常编号", ""),
                "观测值": r.get("观测值", ""),
                "异常评分": r.get("异常评分", ""),
                "确认时间": r.get("确认时间", ""),
            }
            for r in store.rows(self.MODULE)
            if r.get("指标编码") == metric_code and r.get("status") == "已确认"
        ]

    # ---- 业务扩展：从已确认异常日志发起异常调查（进入案件工作台） ----

    def launch_investigation(
        self,
        entry_id: int,
        source_code: str,
        event_code: str,
        window_key: str = "",
        *,
        source_name: str = "",
        evidence: str = "",
    ) -> dict[str, Any]:
        """异常调查入口：仅已确认的异常日志可发起，转交异常案件工作台归并建案。

        窗口标识缺省时取异常事件自身的基线区间，保证同一窗口的重复证据
        在服务端归并到同一案件。
        """
        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return {"ok": False, "message": f"异常事件 {entry_id} 不存在"}
        if entry.get("status") != "已确认":
            return {"ok": False, "message": "仅已确认的异常日志可发起异常调查"}
        if not source_code.strip() or not event_code.strip():
            return {"ok": False, "message": "来源标识与事件编码为必填"}
        metric_code = str(entry.get("指标编码", ""))
        resolved_window = window_key.strip() or str(entry.get("基线区间", "")) or "默认窗口"

        from app.services.anomaly_case import AnomalyCaseService

        result = AnomalyCaseService().open_investigation(
            metric_code=metric_code,
            window_key=resolved_window,
            source_code=source_code.strip(),
            event_code=event_code.strip(),
            anomaly_id=entry_id,
            source_name=source_name.strip(),
            evidence=evidence.strip(),
        )
        if result.get("ok"):
            entry["调查案件编号"] = result["case"]["案件编号"]
        return result
