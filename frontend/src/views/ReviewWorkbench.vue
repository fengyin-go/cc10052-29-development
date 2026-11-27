<template>
  <section class="page" data-module="conclusion_review_workbench">
    <header class="page-head">
      <div>
        <h2>异常案件评审工作台</h2>
        <p class="page-desc">
          领取异常案件工作台交付的可评审案件，按实际已领用的独立来源生成后续风险处置动作；
          处置数据可回查每个独立异常来源，并按领取时点证据复查。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="reload">刷新队列</button>
      </div>
    </header>

    <!-- 可评审案件：评审入口领取关联案件明细 -->
    <section class="detail-card">
      <h3>可评审案件队列</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>案件编号</th><th>指标编码</th><th>窗口标识</th><th>当前有效来源</th>
            <th>影响次数</th><th>失效原因</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in reviewable" :key="row.id">
            <td>{{ row.案件编号 }}</td>
            <td>{{ row.指标编码 }}</td>
            <td>{{ row.窗口标识 }}</td>
            <td>
              <span v-for="code in activeCodes(row.id)" :key="code" class="chip chip-active">{{ code }}</span>
            </td>
            <td>{{ row.影响次数 }}</td>
            <td>{{ row.失效原因 || '—' }}</td>
            <td>
              <button class="btn primary" type="button" :data-testid="`claim-case-${row.id}`" @click="claim(row.id)">
                领取案件明细
              </button>
            </td>
          </tr>
          <tr v-if="!reviewable.length">
            <td colspan="7" class="empty-state">暂无可评审案件（无有效来源的案件不会进入领用队列）</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 已领取的案件评审记录 -->
    <section class="detail-card">
      <h3>案件评审记录与处置</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>记录编号</th><th>案件/指标/窗口</th><th>状态</th><th>实际领用来源</th>
            <th>已生成处置</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="rv in caseReviews" :key="rv.id">
            <td>{{ rv.记录编号 }}</td>
            <td>{{ rv.案件编号 }}<div class="muted-text">{{ rv.指标编码 }} · {{ rv.窗口标识 }}</div></td>
            <td><span class="status-badge" :class="rv.status === '已通过' ? 'badge-ok' : rv.status === '已驳回' ? 'badge-invalid' : 'badge-progress'">{{ rv.status }}</span></td>
            <td>
              <span v-for="code in (rv.领用来源标识 as string[])" :key="code" class="chip chip-active">{{ code }}</span>
            </td>
            <td>{{ (rv.处置动作 as string[] | undefined)?.length ?? 0 }} 条</td>
            <td class="row-actions">
              <template v-if="rv.status === '待评审'">
                <button class="link" type="button" @click="handle(Number(rv.id), '采纳处置')">采纳处置</button>
                <button class="link" type="button" @click="handle(Number(rv.id), '退回核实')">退回核实</button>
              </template>
              <button class="link" type="button" @click="trace(Number(rv.id))">证据复查/处置回查</button>
            </td>
          </tr>
          <tr v-if="!caseReviews.length">
            <td colspan="6" class="empty-state">尚未领取案件</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 证据复查：处置数据回查每个独立异常来源 -->
    <section v-if="traceData" class="detail-card">
      <h3>证据复查：{{ traceData.review.记录编号 }}</h3>
      <p class="page-desc">
        领取时点冻结来源 {{ (traceData.review.领用来源标识 as string[]).join('、') }}，
        处置仅作用于指标 {{ traceData.review.指标编码 }} 的窗口 {{ traceData.review.窗口标识 }}。
      </p>
      <table class="data-table">
        <thead>
          <tr>
            <th>处置编号</th><th>独立来源</th><th>事件编码</th><th>处置类型</th>
            <th>处置说明</th><th>处置时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="action in traceData.actions" :key="String(action.id)">
            <td>{{ action.处置编号 }}</td>
            <td>{{ action.来源标识 }}</td>
            <td>{{ action.事件编码 }}</td>
            <td>{{ action.处置类型 }}</td>
            <td>{{ action.处置说明 }}</td>
            <td>{{ action.处置时间 }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <footer class="page-foot">
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  claimCase,
  getReviewableQueue,
  handleCaseReview,
  listReviews,
  traceReviewEvidence,
  type AnomalyCase,
} from '@/api/case-workbench'

type CaseReviewRow = Record<string, unknown> & { id: number }

const reviewable = ref<AnomalyCase[]>([])
const caseReviews = ref<CaseReviewRow[]>([])
const traceData = ref<Awaited<ReturnType<typeof traceReviewEvidence>> | null>(null)
const errorMessage = ref('')
const sourceMap = ref<Record<number, string[]>>({})

function activeCodes(caseId: number): string[] {
  return sourceMap.value[caseId] ?? []
}

async function reload() {
  errorMessage.value = ''
  try {
    const queue = await getReviewableQueue()
    reviewable.value = queue.items
    // 案件列表本身只给数量，逐案取详情得到当前有效来源标识。
    const map: Record<number, string[]> = {}
    for (const c of queue.items) {
      const detail = await (await fetch(`/api/anomaly_case/${c.id}/detail`)).json()
      if (detail.ok) {
        map[c.id] = detail.case.sources
          .filter((s: { 有效性: string }) => s.有效性 === '有效')
          .map((s: { 来源标识: string }) => s.来源标识)
          .sort()
      }
    }
    sourceMap.value = map
    const reviews = await listReviews({ size: '200' })
    caseReviews.value = reviews.items.filter((r) => r.评审类型 === '异常案件评审') as CaseReviewRow[]
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '评审队列读取失败'
  }
}

async function claim(caseId: number) {
  const result = await claimCase(caseId)
  if (!result.ok) {
    errorMessage.value = result.message
    window.alert(result.message)
    return
  }
  errorMessage.value = ''
  await reload()
}

async function handle(reviewId: number, decision: string) {
  const remark = window.prompt(`${decision}说明`, decision === '采纳处置' ? '按实际领用来源执行风险处置' : '退回来源补证核实') ?? ''
  const result = await handleCaseReview(reviewId, decision, remark)
  if (!result.ok) {
    errorMessage.value = result.message
    window.alert(result.message)
    return
  }
  errorMessage.value = ''
  await reload()
  await trace(reviewId)
}

async function trace(reviewId: number) {
  traceData.value = await traceReviewEvidence(reviewId)
}

onMounted(reload)
</script>
