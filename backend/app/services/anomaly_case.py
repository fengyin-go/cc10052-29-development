"""异常案件工作台领域服务：从已确认异常日志发起调查，按同窗口归并证据、核对来源。

数据链路位置：质量处置层，承接指标异常检测的确认结果，把多个独立来源上报的
同一窗口事件归并为可核对、可评审的案件；服务端负责重复证据归并（保留各独立
来源、相同事件重报不叠加影响次数）、来源撤回与案件失效判定，再把可评审案件
交付结论评审队列实际领用。

关键不变量：
1. 案件按「指标编码 + 窗口标识」归并；不同指标同窗口的异常必须各自成案。
2. 同一来源对同一事件的重报只增加上报次数，影响次数按去重事件数计算。
3. 跨来源校验单要求同一指标下至少两个【当前有效】的独立来源；已撤回来源
   的源材料保留，但不得再用于新的跨来源校验单。
4. 全部来源撤回后案件失效并给出失效原因；重新获得有效来源时自动恢复可评审。
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


class AnomalyCaseService(BaseModuleService):
    MODULE = "anomaly_case"
    ENTITY = "异常案件"
    OPERATION_TERM = "归并"
    LIST_FIELDS = ["案件编号", "指标编码", "窗口标识", "案件状态", "有效来源数", "影响次数"]
    REQUIRED_FIELDS = ["案件编号", "指标编码", "窗口标识"]
    STATUS_ORDER = ["待调查", "调查中", "可评审", "已评审", "已失效"]
    ACTION_RULES: dict[str, str] = {}
    NEGATIVE_ACTIONS: list[str] = []

    # ---- 工具：派生统计与案件状态 ----

    def _active_sources(self, case_id: int) -> list[dict[str, Any]]:
        return [
            s for s in store.rows("anomaly_source")
            if int(s.get("案件id", 0)) == case_id and s.get("有效性") == "有效"
        ]

    def _all_sources(self, case_id: int) -> list[dict[str, Any]]:
        return [
            s for s in store.rows("anomaly_source")
            if int(s.get("案件id", 0)) == case_id
        ]

    def _refresh_case(self, case: dict[str, Any]) -> dict[str, Any]:
        """按来源当前有效性重算案件统计、失效状态与失效原因。"""
        sources = self._all_sources(int(case.get("id", 0)))
        active = [s for s in sources if s.get("有效性") == "有效"]
        case["来源总数"] = str(len(sources))
        case["有效来源数"] = str(len(active))
        # 影响次数 = 所有来源中去重的独立异常事件数；相同事件重报不叠加。
        distinct_events = {str(s.get("事件编码", "")) for s in sources if s.get("事件编码")}
        case["影响次数"] = str(len(distinct_events))
        # 上报次数保留重报累计，供核对「重复证据归并」使用。
        case["上报总次数"] = str(sum(int(s.get("上报次数", "1") or 1) for s in sources))
        if not sources:
            case["案件状态"] = "已失效"
            case["失效原因"] = "案件没有任何可核对来源"
        elif not active:
            case["案件状态"] = "已失效"
            case["失效原因"] = "全部来源已撤回，无有效来源支撑该案件"
        else:
            case["失效原因"] = ""
            if case.get("案件状态") == "已失效":
                # 重新获得有效来源：回到可评审（此前已完成的调查历史保留）。
                case["案件状态"] = "可评审"
        case["abnormal"] = case.get("案件状态") == "已失效"
        case["pending"] = case.get("案件状态") in ("待调查", "调查中", "可评审")
        return case

    def _find_case(self, metric_code: str, window_key: str) -> dict[str, Any] | None:
        return next(
            (c for c in store.rows(self.MODULE)
             if c.get("指标编码") == metric_code and c.get("窗口标识") == window_key),
            None,
        )

    # ---- 入口：从已确认异常日志发起异常调查 ----

    def open_investigation(
        self,
        metric_code: str,
        window_key: str,
        source_code: str,
        event_code: str,
        *,
        anomaly_id: int | None = None,
        source_name: str = "",
        evidence: str = "",
    ) -> dict[str, Any]:
        """从一条已确认异常日志发起调查：服务端按同窗口归并到既有/新案件并登记来源。"""
        if not metric_code or not window_key or not source_code or not event_code:
            return {"ok": False, "message": "指标编码、窗口标识、来源标识、事件编码均为必填"}
        # 入口必须来自已确认的异常日志（若提供异常 id，则强校验状态）。
        if anomaly_id is not None:
            anomaly = store.find("anomaly_metric", int(anomaly_id))
            if anomaly is None:
                return {"ok": False, "message": "关联的异常日志不存在"}
            if anomaly.get("status") != "已确认":
                return {"ok": False, "message": "仅已确认的异常日志可发起异常调查"}
        case = self._find_case(metric_code, window_key)
        created = False
        if case is None:
            case = {
                "id": _next_id(self.MODULE),
                "案件编号": f"CASE-{metric_code}-{window_key}",
                "指标编码": metric_code,
                "窗口标识": window_key,
                "案件状态": "待调查",
                "来源异常id": str(anomaly_id or ""),
                "建案时间": _now(),
                "来源总数": "0",
                "有效来源数": "0",
                "影响次数": "0",
                "上报总次数": "0",
                "失效原因": "",
                "status": "待调查",
                "pending": True,
                "abnormal": False,
            }
            store.rows(self.MODULE).append(case)
            created = True
        result = self.submit_source(
            int(case["id"]), source_code, event_code,
            source_name=source_name, evidence=evidence,
        )
        if not result.get("ok"):
            return result
        case = store.find(self.MODULE, int(case["id"]))
        assert case is not None
        if anomaly_id is not None:
            case["来源异常id"] = str(anomaly_id)
        return {
            "ok": True,
            "message": ("已建新案件并受理首个来源" if created else "同窗口证据已归并到既有案件")
                       + f"：{case['案件编号']}",
            "case": case,
            "source": result.get("source"),
            "created": created,
        }

    # ---- 证据来源登记：重复证据归并、重报不叠加影响 ----

    def submit_source(
        self,
        case_id: int,
        source_code: str,
        event_code: str,
        *,
        source_name: str = "",
        evidence: str = "",
    ) -> dict[str, Any]:
        """向案件提交一个独立来源的证据；同来源同事件重报只累计上报次数。"""
        case = store.find(self.MODULE, case_id)
        if case is None:
            return {"ok": False, "message": f"案件 {case_id} 不存在"}
        if not source_code or not event_code:
            return {"ok": False, "message": "来源标识与事件编码为必填"}
        source_rows = store.rows("anomaly_source")
        existing = next(
            (s for s in source_rows
             if int(s.get("案件id", 0)) == case_id
             and s.get("来源标识") == source_code
             and s.get("事件编码") == event_code),
            None,
        )
        if existing is not None:
            # 相同事件重报：保留独立来源，仅累计上报次数，影响次数不叠加。
            existing["上报次数"] = str(int(existing.get("上报次数", "1") or 1) + 1)
            existing["最近上报时间"] = _now()
            if evidence:
                existing["证据材料"] = evidence
            # 撤回后重新上报等同于该来源恢复有效（源材料仍可核对）。
            if existing.get("有效性") != "有效":
                existing["有效性"] = "有效"
                existing["撤回原因"] = ""
            self._refresh_case(case)
            return {"ok": True, "message": "相同事件重报已归并，影响次数不叠加", "source": existing}
        source = {
            "id": _next_id("anomaly_source"),
            "案件id": case_id,
            "来源编号": f"SRC-{case_id}-{source_code}",
            "来源标识": source_code,
            "来源名称": source_name or source_code,
            "事件编码": event_code,
            "证据材料": evidence,
            "有效性": "有效",
            "上报次数": "1",
            "首次上报时间": _now(),
            "最近上报时间": _now(),
            "撤回时间": "",
            "撤回原因": "",
            "status": "有效",
            "pending": False,
            "abnormal": False,
        }
        source_rows.append(source)
        self._refresh_case(case)
        return {"ok": True, "message": "新独立来源已受理并归并到案件", "source": source}

    def withdraw_source(self, source_id: int, reason: str) -> dict[str, Any]:
        """撤回来源当前有效性：源材料保留，案件据此重算有效来源与失效状态。"""
        source = store.find("anomaly_source", source_id)
        if source is None:
            return {"ok": False, "message": f"来源 {source_id} 不存在"}
        if source.get("有效性") != "有效":
            return {"ok": False, "message": "仅当前有效的来源可撤回"}
        if not reason.strip():
            return {"ok": False, "message": "撤回来源必须填写撤回原因"}
        source["有效性"] = "已撤回"
        source["status"] = "已撤回"
        source["abnormal"] = True
        source["撤回时间"] = _now()
        source["撤回原因"] = reason.strip()
        case = store.find(self.MODULE, int(source.get("案件id", 0)))
        if case is not None:
            self._refresh_case(case)
        return {"ok": True, "message": f"来源 {source.get('来源标识')} 已撤回，源材料保留可核对", "source": source}

    # ---- 调查/校验单：跨来源校验、单源改办、撤回核实 ----

    def create_investigation(
        self,
        case_id: int,
        investigation_type: str,
        *,
        basis: str = "",
    ) -> dict[str, Any]:
        """发起调查/校验单。类型：跨来源校验单 / 单源调查单。

        跨来源校验单必须基于至少两个当前有效且相互独立的来源；已撤回来源
        不得用于新的跨来源校验单。
        """
        case = store.find(self.MODULE, case_id)
        if case is None:
            return {"ok": False, "message": f"案件 {case_id} 不存在"}
        active = self._active_sources(case_id)
        if not active:
            return {"ok": False, "message": "案件没有有效来源，不能发起调查"}
        distinct_active_sources = {s.get("来源标识") for s in active}
        if investigation_type == "跨来源校验单":
            if len(distinct_active_sources) < 2:
                return {
                    "ok": False,
                    "message": "跨来源校验单需要两个及以上当前有效的独立来源",
                }
        elif investigation_type == "单源调查单":
            if len(distinct_active_sources) != 1:
                return {"ok": False, "message": "单源调查单仅适用于当前只有一个有效来源的案件"}
        else:
            return {"ok": False, "message": "调查类型必须是跨来源校验单或单源调查单"}
        rows = store.rows("anomaly_investigation")
        investigation = {
            "id": _next_id("anomaly_investigation"),
            "校验单编号": f"CHK-{case_id}-{len(rows) + 1:02d}",
            "案件id": case_id,
            "案件编号": case.get("案件编号", ""),
            "指标编码": case.get("指标编码", ""),
            "窗口标识": case.get("窗口标识", ""),
            "调查类型": investigation_type,
            "校验单状态": "已申请",
            "申请说明": basis,
            "申请时间": _now(),
            "领用来源": sorted(distinct_active_sources),
            # 申请时点证据快照：来源材料连同有效性一起冻结，供事后按当时证据复查。
            "证据快照": [
                {
                    "来源标识": s.get("来源标识"),
                    "事件编码": s.get("事件编码"),
                    "有效性": s.get("有效性"),
                    "上报次数": s.get("上报次数"),
                }
                for s in self._all_sources(case_id)
            ],
            "冲突标记": False,
            "冲突说明": "",
            "办理出路": "",
            "status": "已申请",
            "pending": True,
            "abnormal": False,
        }
        rows.append(investigation)
        if case.get("案件状态") == "待调查":
            case["案件状态"] = "调查中"
            case["status"] = "调查中"
        return {"ok": True, "message": f"{investigation_type} {investigation['校验单编号']} 已受理", "investigation": investigation}

    def claim_investigation(self, investigation_id: int) -> dict[str, Any]:
        """领取已申请的调查：把申请时点快照与当前有效来源比对，冲突时显式标记。"""
        investigation = store.find("anomaly_investigation", investigation_id)
        if investigation is None:
            return {"ok": False, "message": f"校验单 {investigation_id} 不存在"}
        if investigation.get("校验单状态") != "已申请":
            return {"ok": False, "message": "仅已申请的调查可领取"}
        case = store.find(self.MODULE, int(investigation.get("案件id", 0)))
        current_active = sorted({s.get("来源标识") for s in self._active_sources(int(investigation.get("案件id", 0)))}) if case else []
        snapshot = investigation.get("证据快照", [])
        snapshot_active = sorted({s.get("来源标识") for s in snapshot if s.get("有效性") == "有效"})
        withdrawn_since = [
            s.get("来源标识") for s in snapshot
            if s.get("有效性") == "有效" and s.get("来源标识") not in current_active
        ]
        conflict = bool(withdrawn_since)
        investigation["校验单状态"] = "已领取"
        investigation["status"] = "已领取"
        investigation["领取时间"] = _now()
        investigation["当前有效来源"] = current_active
        investigation["冲突标记"] = conflict
        investigation["冲突说明"] = (
            "申请后来源撤回：" + "、".join(withdrawn_since) if conflict else ""
        )
        return {
            "ok": True,
            "message": "调查已领取，原申请与当前有效来源存在冲突" if conflict else "调查已领取，来源与申请时点一致",
            "investigation": investigation,
            "conflict": conflict,
            "withdrawn_since": withdrawn_since,
        }

    def verify_withdrawal(self, investigation_id: int, note: str) -> dict[str, Any]:
        """出路一：实际产生核实撤回原因的历史校验单，追溯撤回来源的撤回原因。"""
        investigation = store.find("anomaly_investigation", investigation_id)
        if investigation is None or investigation.get("校验单状态") != "已领取":
            return {"ok": False, "message": "仅已领取的调查可办理"}
        case_id = int(investigation.get("案件id", 0))
        withdrawn = [s for s in self._all_sources(case_id) if s.get("有效性") == "已撤回"]
        if not withdrawn:
            return {"ok": False, "message": "当前没有已撤回来源，无需撤回核实"}
        investigation["校验单状态"] = "已办理"
        investigation["status"] = "已办理"
        investigation["pending"] = False
        investigation["办理出路"] = "核实撤回原因"
        investigation["办理说明"] = note
        investigation["办理时间"] = _now()
        investigation["核实记录"] = [
            {
                "来源标识": s.get("来源标识"),
                "撤回原因": s.get("撤回原因"),
                "撤回时间": s.get("撤回时间"),
            }
            for s in withdrawn
        ]
        self._mark_case_reviewable(case_id)
        return {"ok": True, "message": "已生成核实撤回原因的历史校验单，源材料与撤回原因可追溯", "investigation": investigation}

    def convert_to_single_source(self, investigation_id: int, note: str) -> dict[str, Any]:
        """出路二：冲突后按当前唯一有效来源改办为单源调查。"""
        investigation = store.find("anomaly_investigation", investigation_id)
        if investigation is None or investigation.get("校验单状态") != "已领取":
            return {"ok": False, "message": "仅已领取的调查可办理"}
        case_id = int(investigation.get("案件id", 0))
        active = self._active_sources(case_id)
        distinct = {s.get("来源标识") for s in active}
        if len(distinct) != 1:
            return {"ok": False, "message": "仅当当前有效来源唯一时才可按单源改办"}
        investigation["校验单状态"] = "已办理"
        investigation["status"] = "已办理"
        investigation["pending"] = False
        investigation["办理出路"] = "按当前单源改办"
        investigation["办理说明"] = note
        investigation["办理时间"] = _now()
        investigation["改办来源"] = sorted(distinct)
        self._mark_case_reviewable(case_id)
        return {"ok": True, "message": f"已按当前有效来源 {sorted(distinct)[0]} 单源改办", "investigation": investigation}

    def _mark_case_reviewable(self, case_id: int) -> None:
        case = store.find(self.MODULE, case_id)
        if case is None:
            return
        self._refresh_case(case)
        if case.get("案件状态") not in ("已失效", "已评审") and self._active_sources(case_id):
            case["案件状态"] = "可评审"
            case["status"] = "可评审"

    def mark_reviewed(self, case_id: int) -> None:
        """评审领用并办结后回调：案件置为已评审，处理结果仍可按快照复查。"""
        case = store.find(self.MODULE, case_id)
        if case is not None:
            case["案件状态"] = "已评审"
            case["status"] = "已评审"
            case["pending"] = False

    # ---- 查询：案件详情、指标概览 ----

    def case_detail(self, case_id: int) -> dict[str, Any] | None:
        case = store.find(self.MODULE, case_id)
        if case is None:
            return None
        sources = self._all_sources(case_id)
        investigations = [
            i for i in store.rows("anomaly_investigation")
            if int(i.get("案件id", 0)) == case_id
        ]
        reviews = [
            r for r in store.rows("conclusion_review")
            if int(r.get("关联案件id", 0) or 0) == case_id
        ]
        return {
            **case,
            "sources": sources,
            "investigations": investigations,
            "reviews": reviews,
        }

    def metric_overview(self, metric_code: str) -> dict[str, Any]:
        """单指标概览：只列【当前有效】来源与可发起的调查类型，撤回来源不参与新单。"""
        cases = [c for c in store.rows(self.MODULE) if c.get("指标编码") == metric_code]
        payload = []
        for case in cases:
            self._refresh_case(case)
            active_sources = self._active_sources(int(case["id"]))
            distinct_active = sorted({s.get("来源标识") for s in active_sources})
            payload.append({
                "案件编号": case.get("案件编号"),
                "窗口标识": case.get("窗口标识"),
                "案件状态": case.get("案件状态"),
                "有效来源": distinct_active,
                "失效原因": case.get("失效原因", ""),
                "影响次数": case.get("影响次数"),
                "可发起调查": (
                    "跨来源校验单" if len(distinct_active) >= 2
                    else "单源调查单" if len(distinct_active) == 1
                    else "无（无有效来源）"
                ),
            })
        return {"ok": True, "指标编码": metric_code, "案件": payload}

    def reviewable_cases(self) -> list[dict[str, Any]]:
        """交付结论评审队列实际领用的可评审案件清单。"""
        rows = []
        for case in store.rows(self.MODULE):
            self._refresh_case(case)
            if case.get("案件状态") == "可评审" and self._active_sources(int(case["id"])):
                rows.append(case)
        return rows
