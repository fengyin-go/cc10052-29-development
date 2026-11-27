<template>
  <div v-if="detail" class="case-detail">
    <section class="detail-card">
      <h3>{{ detail.案件编号 }}</h3>
      <dl class="info-grid">
        <div><dt>指标编码</dt><dd>{{ detail.指标编码 }}</dd></div>
        <div><dt>窗口标识</dt><dd>{{ detail.窗口标识 }}</dd></div>
        <div><dt>案件状态</dt><dd><span class="status-badge" :class="badgeClass(detail.案件状态)">{{ detail.案件状态 }}</span></dd></div>
        <div><dt>影响次数</dt><dd>{{ detail.影响次数 }}（去重事件，重报不叠加）</dd></div>
        <div><dt>上报总次数</dt><dd>{{ detail.上报总次数 }}</dd></div>
        <div><dt>有效来源</dt><dd>{{ detail.有效来源数 }} / {{ detail.来源总数 }}</dd></div>
        <div class="full-row"><dt>失效原因</dt><dd :class="{ 'error-text': detail.失效原因 }">{{ detail.失效原因 || '—' }}</dd></div>
      </dl>
    </section>

    <!-- 指标概览：只列当前有效来源，撤回来源不出现在新单候选里 -->
    <section class="detail-card">
      <h3>当前有效来源概览</h3>
      <p class="page-desc">新发起的调查只能使用当前有效来源；已撤回来源仅保留材料供核对。</p>
      <ul class="source-chips">
        <li v-for="code in activeSourceCodes" :key="code" class="chip chip-active">{{ code }}</li>
        <li v-if="!activeSourceCodes.length" class="muted-text">无有效来源，不能发起新调查</li>
      </ul>
      <p class="page-desc">
        当前可发起：
        <strong>{{ activeSourceCodes.length >= 2 ? '跨来源校验单' : activeSourceCodes.length === 1 ? '单源调查单' : '无（无有效来源）' }}</strong>
      </p>
      <div class="row-actions">
        <button class="btn primary" type="button" :disabled="activeSourceCodes.length < 2" @click="createInvestigation('跨来源校验单')">
          发起跨来源校验单
        </button>
        <button class="btn" type="button" :disabled="activeSourceCodes.length !== 1" @click="createInvestigation('单源调查单')">
          发起单源调查单
        </button>
        <button class="btn" type="button" @click="showAddSource = !showAddSource">补报来源证据</button>
        <button class="btn" type="button" @click="goReview">前往评审队列领用</button>
      </div>

      <form v-if="showAddSource" class="inline-form" @submit.prevent="addSource">
        <input v-model="newSource.source_code" placeholder="来源标识（必填）" required />
        <input v-model="newSource.event_code" placeholder="事件编码（必填）" required />
        <input v-model="newSource.source_name" placeholder="来源名称" />
        <input v-model="newSource.evidence" placeholder="证据材料" />
        <button class="btn primary" type="submit">提交来源</button>
      </form>
    </section>

    <!-- 独立来源明细：可分辨来源差异与撤回情况 -->
    <section class="detail-card">
      <h3>独立来源与撤回明细（{{ detail.sources.length }}）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>来源标识</th><th>来源名称</th><th>事件编码</th><th>有效性</th>
            <th>上报次数</th><th>证据材料</th><th>撤回原因/时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="source in detail.sources" :key="source.id" :data-valid="source.有效性">
            <td>{{ source.来源标识 }}</td>
            <td>{{ source.来源名称 }}</td>
            <td>{{ source.事件编码 }}</td>
            <td>
              <span class="status-badge" :class="source.有效性 === '有效' ? 'badge-ok' : 'badge-invalid'">
                {{ source.有效性 }}
              </span>
            </td>
            <td>{{ source.上报次数 }}</td>
            <td>{{ source.证据材料 || '—' }}</td>
            <td>
              <template v-if="source.有效性 === '已撤回'">
                <div>{{ source.撤回原因 }}</div>
                <div class="muted-text">{{ source.撤回时间 }}</div>
              </template>
              <span v-else>—</span>
            </td>
            <td>
              <button v-if="source.有效性 === '有效'" class="link" type="button" @click="withdraw(source.id)">
                撤回当前有效性
              </button>
              <span v-else class="muted-text">源材料保留</span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 调查/校验单：申请时点快照、冲突标记与两条办理出路 -->
    <section class="detail-card">
      <h3>调查 / 校验单（{{ detail.investigations.length }}）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>校验单编号</th><th>类型</th><th>状态</th><th>申请时点来源</th>
            <th>当前有效来源</th><th>冲突</th><th>办理出路</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="inv in detail.investigations" :key="inv.id">
            <td>{{ inv.校验单编号 }}</td>
            <td>{{ inv.调查类型 }}</td>
            <td>{{ inv.校验单状态 }}</td>
            <td>
              <span v-for="s in inv.证据快照" :key="s.来源标识"
                    class="chip" :class="s.有效性 === '有效' ? 'chip-active' : 'chip-withdrawn'">
                {{ s.来源标识 }}（{{ s.有效性 }}）
              </span>
            </td>
            <td>{{ (inv.当前有效来源 ?? activeSourceCodes).join('、') || '无' }}</td>
            <td>
              <span v-if="inv.冲突标记" class="status-badge badge-invalid">冲突：{{ inv.冲突说明 }}</span>
              <span v-else>—</span>
            </td>
            <td>
              <div v-if="inv.办理出路">{{ inv.办理出路 }}</div>
              <div v-if="inv.核实记录" class="muted-text">
                <div v-for="r in inv.核实记录" :key="r.来源标识">
                  {{ r.来源标识 }} 撤回原因：{{ r.撤回原因 }}
                </div>
              </div>
              <div v-if="inv.改办来源" class="muted-text">改办来源：{{ inv.改办来源.join('、') }}</div>
            </td>
            <td class="row-actions">
              <button v-if="inv.校验单状态 === '已申请'" class="link" type="button" @click="claim(inv.id)">
                领取调查
              </button>
              <template v-if="inv.校验单状态 === '已领取'">
                <button class="link" type="button" @click="onVerifyWithdrawal(inv.id)">核实撤回原因</button>
                <button class="link" type="button" :disabled="activeSourceCodes.length !== 1" @click="onConvertSingle(inv.id)">
                  按当前单源改办
                </button>
              </template>
              <span v-else-if="inv.校验单状态 === '已办理'" class="muted-text">已办理</span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  claimInvestigation,
  convertSingleSource,
  createInvestigation as apiCreateInvestigation,
  getCaseDetail,
  submitSource,
  verifyWithdrawal as verifyWithdrawalApi,
  withdrawSource,
  type CaseDetail,
} from '@/api/case-workbench'

const props = defineProps<{ caseId: number }>()
const emit = defineEmits<{ (e: 'refresh'): void; (e: 'go-review'): void }>()

const detail = ref<CaseDetail | null>(null)
const errorMessage = ref('')
const showAddSource = ref(false)
const newSource = ref({ source_code: '', event_code: '', source_name: '', evidence: '' })

const activeSourceCodes = computed(() =>
  detail.value ? detail.value.sources.filter((s) => s.有效性 === '有效').map((s) => s.来源标识).sort() : [],
)

function badgeClass(status: string): string {
  if (status === '已失效') return 'badge-invalid'
  if (status === '可评审' || status === '已评审') return 'badge-ok'
  return 'badge-progress'
}

async function load() {
  const payload = await getCaseDetail(props.caseId)
  if (!payload.ok) {
    errorMessage.value = payload.message || '案件详情读取失败'
    return
  }
  detail.value = payload.case
}

async function run(action: () => Promise<{ ok: boolean; message: string }>) {
  const result = await action()
  if (!result.ok) {
    errorMessage.value = result.message
    window.alert(result.message)
    return
  }
  errorMessage.value = ''
  await load()
  emit('refresh')
}

function createInvestigation(type: string) {
  void run(() => apiCreateInvestigation(props.caseId, type))
}

function addSource() {
  void run(async () => {
    const result = await submitSource(props.caseId, { ...newSource.value })
    if (result.ok) {
      newSource.value = { source_code: '', event_code: '', source_name: '', evidence: '' }
      showAddSource.value = false
    }
    return result
  })
}

function withdraw(sourceId: number) {
  const reason = window.prompt('请填写撤回原因（源材料会保留）')
  if (reason === null) return
  void run(() => withdrawSource(sourceId, reason))
}

function claim(investigationId: number) {
  void run(async () => {
    const result = await claimInvestigation(investigationId)
    if (result.ok && (result as { conflict?: boolean }).conflict) {
      window.alert(`领取时发现来源冲突：${result.message}`)
    }
    return result
  })
}

function onVerifyWithdrawal(investigationId: number) {
  const note = window.prompt('核实撤回原因说明', '追溯已撤回来源的撤回原因') ?? ''
  void run(() => verifyWithdrawalApi(investigationId, note))
}

function onConvertSingle(investigationId: number) {
  const note = window.prompt('按当前唯一有效来源改办说明', '冲突后按当前单源改办') ?? ''
  void run(() => convertSingleSource(investigationId, note))
}

function goReview() {
  emit('go-review')
}

onMounted(load)
defineExpose({ reload: load })
</script>
