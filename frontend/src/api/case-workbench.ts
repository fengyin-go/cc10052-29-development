/** 异常案件工作台与案件评审的专用接口封装。 */
import { request } from './client'

export type CaseSource = {
  id: number
  案件id: number
  来源编号: string
  来源标识: string
  来源名称: string
  事件编码: string
  证据材料: string
  有效性: '有效' | '已撤回'
  上报次数: string
  首次上报时间: string
  最近上报时间: string
  撤回时间: string
  撤回原因: string
}

export type Investigation = {
  id: number
  校验单编号: string
  案件id: number
  案件编号: string
  指标编码: string
  窗口标识: string
  调查类型: string
  校验单状态: string
  申请说明: string
  申请时间: string
  领用来源: string[]
  证据快照: { 来源标识: string; 事件编码: string; 有效性: string; 上报次数: string }[]
  冲突标记: boolean
  冲突说明: string
  办理出路: string
  办理说明?: string
  办理时间?: string
  当前有效来源?: string[]
  核实记录?: { 来源标识: string; 撤回原因: string; 撤回时间: string }[]
  改办来源?: string[]
}

export type AnomalyCase = {
  id: number
  案件编号: string
  指标编码: string
  窗口标识: string
  案件状态: string
  来源总数: string
  有效来源数: string
  影响次数: string
  上报总次数: string
  失效原因: string
}

export type CaseDetail = AnomalyCase & {
  sources: CaseSource[]
  investigations: Investigation[]
  reviews: Record<string, unknown>[]
}

export type ApiResult<T = Record<string, unknown>> = {
  ok: boolean
  message: string
  entry?: T
}

async function asJson<T = any>(response: Response): Promise<T> {
  return (await response.json()) as T
}

// ---- 指标异常检测：发起调查入口 ----

export function launchFromAnomaly(
  anomalyId: number,
  payload: { source_code: string; event_code: string; window_key?: string; source_name?: string; evidence?: string },
): Promise<ApiResult> {
  return request(`/api/anomaly_metric/${anomalyId}/launch-investigation`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }).then(asJson)
}

// ---- 案件工作台 ----

export function listCases(filters: Record<string, string> = {}): Promise<{
  items: AnomalyCase[]
  total: number
  page: number
  size: number
}> {
  const query = new URLSearchParams(filters).toString()
  return request(`/api/anomaly_case?${query}`).then(asJson)
}

export function getCaseDetail(caseId: number): Promise<{ ok: boolean; case: CaseDetail; message?: string }> {
  return request(`/api/anomaly_case/${caseId}/detail`).then(asJson)
}

export function getMetricCases(metricCode: string): Promise<{
  ok: boolean
  指标编码: string
  案件: {
    案件编号: string
    窗口标识: string
    案件状态: string
    有效来源: string[]
    失效原因: string
    影响次数: string
    可发起调查: string
  }[]
}> {
  return request(`/api/anomaly_case/metric/${encodeURIComponent(metricCode)}/overview`).then(asJson)
}

export function getReviewableQueue(): Promise<{ ok: boolean; items: AnomalyCase[]; total: number }> {
  return request('/api/anomaly_case/reviewable/queue').then(asJson)
}

export function submitSource(
  caseId: number,
  payload: { source_code: string; event_code: string; source_name?: string; evidence?: string },
): Promise<ApiResult> {
  return request(`/api/anomaly_case/${caseId}/sources`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }).then(asJson)
}

export function withdrawSource(sourceId: number, reason: string): Promise<ApiResult> {
  return request(`/api/anomaly_case/sources/${sourceId}/withdraw`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  }).then(asJson)
}

export function createInvestigation(
  caseId: number,
  investigationType: string,
  basis = '',
): Promise<ApiResult<{ investigation: Investigation }>> {
  return request(`/api/anomaly_case/${caseId}/investigations`, {
    method: 'POST',
    body: JSON.stringify({ investigation_type: investigationType, basis }),
  }).then(asJson)
}

export function claimInvestigation(investigationId: number): Promise<ApiResult<{
  investigation: Investigation
  conflict: boolean
  withdrawn_since: string[]
}>> {
  return request(`/api/anomaly_case/investigations/${investigationId}/claim`, {
    method: 'POST',
  }).then(asJson)
}

export function verifyWithdrawal(investigationId: number, note: string): Promise<ApiResult> {
  return request(`/api/anomaly_case/investigations/${investigationId}/verify-withdrawal`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  }).then(asJson)
}

export function convertSingleSource(investigationId: number, note: string): Promise<ApiResult> {
  return request(`/api/anomaly_case/investigations/${investigationId}/convert-single-source`, {
    method: 'POST',
    body: JSON.stringify({ note }),
  }).then(asJson)
}

// ---- 评审办理 ----

export function claimCase(caseId: number): Promise<ApiResult> {
  return request(`/api/conclusion_review/cases/${caseId}/claim`, {
    method: 'POST',
  }).then(asJson)
}

export function handleCaseReview(
  reviewId: number,
  decision: string,
  remark = '',
): Promise<ApiResult> {
  return request(`/api/conclusion_review/${reviewId}/handle-case`, {
    method: 'POST',
    body: JSON.stringify({ decision, remark }),
  }).then(asJson)
}

export function traceReviewEvidence(reviewId: number): Promise<{
  ok: boolean
  review: Record<string, unknown>
  actions: Record<string, unknown>[]
}> {
  return request(`/api/conclusion_review/${reviewId}/evidence`).then(asJson)
}

export function listReviews(filters: Record<string, string> = {}): Promise<{
  items: Record<string, unknown>[]
  total: number
}> {
  const query = new URLSearchParams(filters).toString()
  return request(`/api/conclusion_review?${query}`).then(asJson)
}
