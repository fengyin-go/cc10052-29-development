"""结论评审队列领域服务：管理实验结论的评审流转、角色协同与办结归档。

数据链路位置：评审治理层，是实验结论进入业务决策前的最后一道人工关，消费
报告分发与异常处置的评审请求，把通过结论推送归档。

异常案件扩展：评审入口领取异常案件工作台交付的可评审案件，按案件【实际已
领用】的独立来源逐一生成后续风险处置动作；处置数据回链每个独立异常来源，
已采用案件的处理结果可按领取时点的证据快照复查。不同指标同窗口的案件互相
隔离，评审处置只影响对应指标的对应案件。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_id(table: str) -> int:
    return max((int(row.get("id", 0)) for row in store.rows(table)), default=0) + 1


class ConclusionReviewService(BaseModuleService):
    MODULE = "conclusion_review"
    ENTITY = "评审记录"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["记录编号", "实验编码", "评审结论", "评审角色", "评审时间"]
    REQUIRED_FIELDS = ["记录编号", "实验编码", "评审结论"]
    STATUS_ORDER = ["待评审", "已通过", "已驳回"]
    ACTION_RULES = {"通过记录": "已通过", "驳回记录": "已驳回"}
    NEGATIVE_ACTIONS = ["驳回记录"]

    # ---- 业务扩展：评审流转与结论归档 ----

    def approve(self, entry_id: int, comment: str) -> dict[str, Any]:
        """通过评审记录并把结论推送到实验归档库。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待评审":
            return {"ok": False, "message": "仅待评审记录可通过"}
        entry["status"] = "已通过"
        entry["pending"] = False
        entry["评审时间"] = _now()
        entry["评审意见"] = comment or "同意采纳"
        archive_rows = store.rows("exp_archive")
        archive_rows.append({
            "id": _next_id("exp_archive"),
            "实验编码": entry.get("实验编码", ""),
            "结束时间": _now(),
            "结论摘要": f"评审通过：{entry.get('评审结论', '')}",
            "归档位置": f"review/{entry.get('记录编号', '')}",
            "保留等级": "标准",
            "status": "待归档",
            "pending": True,
            "abnormal": False,
        })
        return {"ok": True, "message": f"记录 {entry.get('记录编号')} 已通过并推送归档"}

    def reject(self, entry_id: int, reason: str) -> dict[str, Any]:
        """驳回评审记录并通知报告分发停止后续分发。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "待评审":
            return {"ok": False, "message": "仅待评审记录可驳回"}
        if not reason.strip():
            return {"ok": False, "message": "驳回必须填写原因"}
        entry["status"] = "已驳回"
        entry["pending"] = False
        entry["abnormal"] = True
        entry["驳回原因"] = reason
        exp_code = str(entry.get("实验编码", ""))
        stalled = [
            r for r in store.rows("report_dist")
            if exp_code and exp_code in str(r.get("报告编码", "")) and r.get("status") == "排队中"
        ]
        for row in stalled:
            row["status"] = "送达失败"
            row["abnormal"] = True
            row["失败原因"] = "结论被驳回，停止分发"
        return {"ok": True, "message": f"记录已驳回，联动停止 {len(stalled)} 条分发"}

    def batch_approve(self) -> dict[str, Any]:
        """批量通过全部待评审记录。"""
        pending = [r for r in store.rows(self.MODULE) if r.get("status") == "待评审"]
        done = sum(1 for r in pending if self.approve(int(r.get("id", 0)), "").get("ok"))
        return {"ok": True, "message": f"批量通过 {done}/{len(pending)} 条评审"}

    def consume_from_report_dist(self, exp_code: str) -> list[dict[str, Any]]:
        """读取报告分发的送达记录，作为评审证据材料。"""
        return [
            {"报告编码": r.get("报告编码", ""), "接收方": r.get("接收方", ""), "送达时间": r.get("送达时间", "")}
            for r in store.rows("report_dist")
            if exp_code and exp_code in str(r.get("报告编码", "")) and r.get("status") == "已送达"
        ]

    def consume_from_anomaly_metric(self, exp_code: str) -> list[dict[str, Any]]:
        """读取指标异常检测的待确认事件，合并进评审材料。"""
        return [
            {"异常编号": r.get("异常编号", ""), "异常评分": r.get("异常评分", "")}
            for r in store.rows("anomaly_metric")
            if r.get("status") in ("待确认", "已确认")
            and exp_code in str(r.get("指标编码", ""))
        ]

    def reopen_rejected(self, entry_id: int) -> dict[str, Any]:
        """重开已驳回记录：修正结论后回到待评审。"""
        entry = store.find(self.MODULE, entry_id)
        if entry is None or entry.get("status") != "已驳回":
            return {"ok": False, "message": "仅已驳回记录可重开"}
        entry["status"] = "待评审"
        entry["pending"] = True
        entry["abnormal"] = False
        entry["重开次数"] = str(int(entry.get("重开次数", "0") or 0) + 1)
        return {"ok": True, "message": f"记录已重开（第 {entry['重开次数']} 次）"}

    def export_review_queue(self) -> list[dict[str, Any]]:
        """导出待评审队列，供指标查询服务展示办结进度。"""
        return [
            {
                "记录编号": r.get("记录编号", ""),
                "实验编码": r.get("实验编码", ""),
                "评审角色": r.get("评审角色", ""),
                "进入时间": r.get("评审时间", ""),
            }
            for r in store.rows(self.MODULE) if r.get("status") == "待评审"
        ]

    # ---- 业务扩展：异常案件领用、处置与证据复查 ----

    def claim_case(self, case_id: int) -> dict[str, Any]:
        """评审入口领取异常案件明细：冻结实际领用来源快照，生成待评审记录。

        只领取案件工作台交付的可评审案件；不同指标同窗口各自成案，领取与
        后续处置只作用于该案件本身。
        """
        # 延迟导入避免与 anomaly_case 服务在模块加载期形成循环依赖。
        from app.services.anomaly_case import AnomalyCaseService

        case_service = AnomalyCaseService()
        case = store.find("anomaly_case", case_id)
        if case is None:
            return {"ok": False, "message": f"案件 {case_id} 不存在"}
        if case.get("案件状态") != "可评审":
            return {"ok": False, "message": "仅可评审状态的案件可领取"}
        active_sources = case_service._active_sources(case_id)
        if not active_sources:
            return {"ok": False, "message": "案件没有有效来源，不能领取"}
        already = next(
            (r for r in store.rows(self.MODULE)
             if int(r.get("关联案件id", 0) or 0) == case_id and r.get("status") == "待评审"),
            None,
        )
        if already is not None:
            return {"ok": False, "message": "该案件已在评审队列待评审，请勿重复领取", "review": already}
        review_rows = store.rows(self.MODULE)
        review = {
            "id": _next_id(self.MODULE),
            "记录编号": f"RV-CASE-{case_id}",
            "实验编码": str(case.get("指标编码", "")),
            "评审结论": f"异常案件 {case.get('案件编号', '')} 待评审处置",
            "评审角色": "数据质量",
            "评审时间": _now(),
            "status": "待评审",
            "pending": True,
            "abnormal": False,
            "评审类型": "异常案件评审",
            "关联案件id": str(case_id),
            "案件编号": case.get("案件编号", ""),
            "指标编码": case.get("指标编码", ""),
            "窗口标识": case.get("窗口标识", ""),
            # 领取时点冻结的证据快照：处置结果日后按当时证据复查。
            "领用来源快照": [dict(s) for s in active_sources],
            "领用来源标识": sorted({s.get("来源标识") for s in active_sources}),
            "处置动作": [],
        }
        review_rows.append(review)
        return {
            "ok": True,
            "message": f"已领取案件 {case.get('案件编号')}，随附 {len(active_sources)} 个有效来源明细",
            "review": review,
        }

    def handle_case_review(self, review_id: int, decision: str, remark: str = "") -> dict[str, Any]:
        """办理案件评审：以实际已领用的来源逐一生成后续风险处置动作。

        每个独立异常来源对应一条可回查的处置数据；评审处置仅影响该案件
        关联指标，不波及其他指标同窗口案件。
        """
        review = store.find(self.MODULE, review_id)
        if review is None:
            return {"ok": False, "message": f"评审记录 {review_id} 不存在"}
        if review.get("评审类型") != "异常案件评审":
            return {"ok": False, "message": "该接口仅办理异常案件评审"}
        if review.get("status") != "待评审":
            return {"ok": False, "message": "仅待评审的案件记录可办理"}
        if decision not in ("采纳处置", "退回核实"):
            return {"ok": False, "message": "处置结论必须是采纳处置或退回核实"}
        case_id = int(review.get("关联案件id", 0) or 0)
        case = store.find("anomaly_case", case_id)
        if case is None:
            return {"ok": False, "message": "关联案件已不存在"}
        claimed_sources = review.get("领用来源快照", [])
        if not claimed_sources:
            return {"ok": False, "message": "该评审记录没有实际领用来源，无法生成处置动作"}
        action_rows = store.rows("risk_action")
        actions = []
        for source in claimed_sources:
            action = {
                "id": _next_id("risk_action"),
                "处置编号": f"ACT-{review_id}-{source.get('来源标识')}",
                "关联评审id": str(review_id),
                "关联案件id": str(case_id),
                "指标编码": review.get("指标编码", ""),
                "窗口标识": review.get("窗口标识", ""),
                "来源标识": source.get("来源标识", ""),
                "来源编号": source.get("来源编号", ""),
                "事件编码": source.get("事件编码", ""),
                "处置类型": decision,
                "处置说明": remark or ("按案件评审结论执行风险处置" if decision == "采纳处置" else "退回来源核实"),
                "处置时间": _now(),
                "证据快照": dict(source),
                "status": "已处置" if decision == "采纳处置" else "待核实",
                "pending": decision == "退回核实",
                "abnormal": decision == "退回核实",
            }
            action_rows.append(action)
            actions.append(action)
        review["status"] = "已通过" if decision == "采纳处置" else "已驳回"
        review["pending"] = False
        review["abnormal"] = decision == "退回核实"
        review["评审时间"] = _now()
        review["评审意见"] = remark or decision
        review["处置动作"] = [a["处置编号"] for a in actions]
        if decision == "采纳处置":
            # 案件采用处理结果：置已评审；来源与快照均保留，支持按当时证据复查。
            from app.services.anomaly_case import AnomalyCaseService
            AnomalyCaseService().mark_reviewed(case_id)
        return {
            "ok": True,
            "message": f"已按 {len(actions)} 个实际领用来源生成处置动作，仅作用于指标 {review.get('指标编码')}",
            "actions": actions,
            "review": review,
        }

    def trace_review_evidence(self, review_id: int) -> dict[str, Any]:
        """回查评审处置数据：每个独立异常来源的处置动作与领取时点证据快照。"""
        review = store.find(self.MODULE, review_id)
        if review is None:
            return {"ok": False, "message": f"评审记录 {review_id} 不存在"}
        actions = [
            a for a in store.rows("risk_action")
            if int(a.get("关联评审id", 0) or 0) == review_id
        ]
        return {
            "ok": True,
            "review": {
                "记录编号": review.get("记录编号"),
                "案件编号": review.get("案件编号"),
                "指标编码": review.get("指标编码"),
                "窗口标识": review.get("窗口标识"),
                "status": review.get("status"),
                "领用来源标识": review.get("领用来源标识", []),
                "领用来源快照": review.get("领用来源快照", []),
            },
            # 处置数据可回查每个独立异常来源。
            "actions": actions,
        }
