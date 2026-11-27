"""端到端核对：W7 双来源撤回冲突场景与案件工作台全部不变量。

运行：python3 -I /workspace/scripts/verify_scenario.py
（需先启动后端：backend/.venv/bin/uvicorn app.main:app --port 8022）
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8022"
PASS, FAIL = 0, 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {label}")
    else:
        FAIL += 1
        print(f"  ✗ {label} {detail}")


def call(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {"ok": False, "message": f"HTTP {exc.code}: {exc.read().decode()[:200]}"}


def get(path: str):
    return call("GET", path)


def post(path: str, body: dict | None = None):
    raw = call("POST", path, body or {})
    # ActionResult 统一包装：业务数据在 entry 内，透传 entry 便于断言。
    if isinstance(raw, dict) and "entry" in raw and isinstance(raw["entry"], dict) and "ok" in raw["entry"]:
        return {**raw["entry"], "ok": raw.get("ok", raw["entry"].get("ok"))}
    return raw


# ---------- 1. 初始状态：W7 有 A、B 两来源，跨来源校验单已申请 ----------
print("1. 初始 W7 案件与来源")
r = get("/api/anomaly_case/1/detail")["case"]
check("W7 案件存在且状态调查中", r["案件状态"] == "调查中", r["案件状态"])
check("W7 影响次数=2（A重报不叠加）", r["影响次数"] == "2", r["影响次数"])
check("W7 上报总次数=3（含重报）", r["上报总次数"] == "3", r["上报总次数"])
src_a = next(s for s in r["sources"] if s["来源标识"] == "A")
check("来源A保留重报次数2", src_a["上报次数"] == "2", src_a["上报次数"])
check("初始有一张已申请跨来源校验单",
      len(r["investigations"]) == 1 and r["investigations"][0]["校验单状态"] == "已申请")

r8 = get("/api/anomaly_case/2/detail")["case"]
check("同窗口WIN07的W8是独立案件", r8["指标编码"] == "W8" and r8["窗口标识"] == "WIN07")

r9 = get("/api/anomaly_case/3/detail")["case"]
check("W9 已失效并展示失效原因",
      r9["案件状态"] == "已失效" and "撤回" in r9["失效原因"], r9.get("失效原因", ""))
check("W9 撤回来源源材料保留",
      all(s["证据材料"] and s["有效性"] == "已撤回" for s in r9["sources"]))

# ---------- 2. B 撤回当前有效性，源材料保留 ----------
print("2. B 撤回")
res = post("/api/anomaly_case/sources/2/withdraw", {"reason": "离线任务重跑，B批次作废"})
check("撤回成功", res["ok"], res["message"])
r = get("/api/anomaly_case/1/detail")["case"]
src_b = next(s for s in r["sources"] if s["来源标识"] == "B")
check("B 标记已撤回且材料/原因保留",
      src_b["有效性"] == "已撤回" and src_b["撤回原因"] and src_b["证据材料"])
check("W7 仍有有效来源A，案件不失效", r["案件状态"] != "已失效", r["案件状态"])
check("W7 有效来源数变为1", r["有效来源数"] == "1", r["有效来源数"])

# ---------- 3. 指标概览：只列有效 A，新请求不得借 B 发跨来源校验单 ----------
print("3. W7 概览与新调查限制")
ov = get("/api/anomaly_case/metric/W7/overview")["案件"]
w7 = next(c for c in ov if c["窗口标识"] == "WIN07")
check("概览只列有效来源A", w7["有效来源"] == ["A"], str(w7["有效来源"]))
check("概览提示仅可单源调查", w7["可发起调查"] == "单源调查单", w7["可发起调查"])
res = post("/api/anomaly_case/1/investigations",
           {"investigation_type": "跨来源校验单", "basis": "尝试借已撤B再开跨来源单"})
check("撤回后新跨来源校验单被拒", not res["ok"], res["message"])
res = post("/api/anomaly_case/1/investigations",
           {"investigation_type": "单源调查单", "basis": "按当前A单源发起"})
check("按A的单源调查单可发起", res["ok"], res["message"])
new_invest_id = res["investigation"]["id"]

# ---------- 4. 领取原跨来源校验单：原申请与当前有效来源冲突 ----------
print("4. 领取原调查的冲突识别")
res = post("/api/anomaly_case/investigations/1/claim")
check("原跨来源校验单领取成功", res["ok"], res["message"])
check("领取时识别冲突（B申请后撤回）", res["conflict"] is True, str(res.get("conflict")))
check("冲突说明点名B", "B" in res["investigation"]["冲突说明"], res["investigation"].get("冲突说明"))
check("当前有效来源只剩A", res["investigation"]["当前有效来源"] == ["A"])
check("证据快照仍保留申请时点A、B均有效",
      {s["来源标识"] for s in res["investigation"]["证据快照"]} == {"A", "B"})
res2 = post("/api/anomaly_case/investigations/1/claim")
check("已领取单不能重复领取", not res2["ok"], res2["message"])

# ---------- 5. 原调查两条出路：核实撤回原因 / 按A单源改办 ----------
print("5. 原调查出路")
res = post("/api/anomaly_case/investigations/1/verify-withdrawal",
           {"note": "追查B撤回原因"})
check("出路一：生成核实撤回原因的历史校验单", res["ok"], res["message"])
check("核实记录含B的撤回原因",
      any(x["来源标识"] == "B" and x["撤回原因"] for x in res["investigation"]["核实记录"]))

post(f"/api/anomaly_case/investigations/{new_invest_id}/claim")
res = post(f"/api/anomaly_case/investigations/{new_invest_id}/convert-single-source",
           {"note": "冲突后按A当前单源改办"})
check("出路二：按当前A单源改办", res["ok"] and res["investigation"]["改办来源"] == ["A"],
      res.get("message", ""))

q = get("/api/anomaly_case/reviewable/queue")
check("办理后W7进入可评审队列", any(i["id"] == 1 for i in q["items"]))

# ---------- 6. 评审领取案件并按实际领用来源生成处置动作 ----------
print("6. 评审领用与处置")
res = post("/api/conclusion_review/cases/1/claim")
check("评审成功领取W7案件", res["ok"], res["message"])
review_id = res["review"]["id"]
check("领取明细只含实际有效来源A",
      res["review"]["领用来源标识"] == ["A"], str(res["review"]["领用来源标识"]))
check("领取快照不含已撤回B",
      all(s["来源标识"] != "B" for s in res["review"]["领用来源快照"]))
res2 = post("/api/conclusion_review/cases/1/claim")
check("案件不可重复领取", not res2["ok"], res2["message"])

res = post(f"/api/conclusion_review/{review_id}/handle-case",
           {"decision": "采纳处置", "remark": "按A来源证据采纳风险处置"})
check("评审办理成功", res["ok"], res["message"])
check("按实际领用来源数生成1条处置动作", len(res["actions"]) == 1, str(len(res["actions"])))
check("处置动作回链独立来源A", res["actions"][0]["来源标识"] == "A")
check("处置仅作用于W7指标", res["actions"][0]["指标编码"] == "W7")

trace = get(f"/api/conclusion_review/{review_id}/evidence")
check("复查返回处置动作与来源快照",
      len(trace["actions"]) == 1 and trace["review"]["领用来源快照"][0]["来源标识"] == "A")
r = get("/api/anomaly_case/1/detail")["case"]
check("采用后案件置已评审", r["案件状态"] == "已评审", r["案件状态"])

# ---------- 7. 另一指标 W8 不受影响，独立领取独立处置 ----------
print("7. 指标隔离")
r8 = get("/api/anomaly_case/2/detail")["case"]
check("W8 仍可评审且来源C有效",
      r8["案件状态"] == "可评审" and any(s["有效性"] == "有效" for s in r8["sources"]))
res = post("/api/conclusion_review/cases/2/claim")
check("W8 可独立领取", res["ok"], res["message"])
w8_review = res["review"]["id"]
res = post(f"/api/conclusion_review/{w8_review}/handle-case",
           {"decision": "退回核实", "remark": "W8来源待补证"})
check("W8 处置仅含来源C且不影响W7",
      len(res["actions"]) == 1 and res["actions"][0]["来源标识"] == "C"
      and res["actions"][0]["指标编码"] == "W8")

# ---------- 8. 从已确认异常日志发起调查的入口 ----------
print("8. 异常日志发起调查入口")
res = post("/api/anomaly_metric/2/launch-investigation",
           {"source_code": "A2", "event_code": "EVT-NEW", "window_key": "WIN07",
            "source_name": "补充来源", "evidence": "补充证据"})
check("已确认异常可发起调查并归并同窗口案件", res["ok"], res["message"])
res = post("/api/anomaly_metric/1/launch-investigation",
           {"source_code": "X", "event_code": "EVT-X", "window_key": "WIN07"})
check("待确认异常不能发起调查", not res["ok"], res["message"])

# 重报不叠加影响
cases = get("/api/anomaly_case")["items"]
new_case = next(c for c in cases if c["指标编码"] == "ANOM-0002")
before = new_case["影响次数"]
post(f"/api/anomaly_case/{new_case['id']}/sources",
     {"source_code": "A2", "event_code": "EVT-NEW"})
cases2 = get("/api/anomaly_case")["items"]
new_case2 = next(c for c in cases2 if c["id"] == new_case["id"])
check("相同事件重报影响次数不叠加", new_case2["影响次数"] == before,
      f"{before} -> {new_case2['影响次数']}")

# ---------- 9. 失效案件重新获得来源后恢复 ----------
print("9. 失效恢复")
res = post("/api/anomaly_case/3/sources",
           {"source_code": "F", "event_code": "EVT-903", "source_name": "补报来源F"})
check("失效案件补入有效来源", res["ok"], res["message"])
r9b = get("/api/anomaly_case/3/detail")["case"]
check("补来源后案件恢复可评审", r9b["案件状态"] == "可评审", r9b["案件状态"])
check("失效原因已清除", r9b["失效原因"] == "", r9b.get("失效原因", ""))
check("历史撤回来源D/E材料仍保留",
      {s["来源标识"] for s in r9b["sources"]} >= {"D", "E", "F"})

print(f"\n结果：通过 {PASS} 项，失败 {FAIL} 项")
sys.exit(1 if FAIL else 0)
