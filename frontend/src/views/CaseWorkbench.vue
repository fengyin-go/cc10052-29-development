<template>
  <section class="page" data-module="anomaly_case">
    <header class="page-head">
      <div>
        <h2>异常案件工作台</h2>
        <p class="page-desc">
          从已确认异常日志发起调查，服务端按同窗口归并重复证据并保留各独立来源，
          交付可评审案件供结论评审队列领用。
        </p>
      </div>
      <div class="page-actions">
        <button v-if="selectedCase" class="btn" type="button" @click="closeDetail">返回案件列表</button>
      </div>
    </header>

    <!-- 案件列表 -->
    <template v-if="!selectedCase">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">案件总数</span>
          <strong class="stat-value">{{ cases.length }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">可评审</span>
          <strong class="stat-value">{{ reviewableCount }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">已失效（无有效来源）</span>
          <strong class="stat-value">{{ invalidCount }}</strong>
        </article>
      </div>

      <form class="filter-bar" @submit.prevent="reload">
        <label class="filter-item">
          <span>指标编码</span>
          <input v-model="metricFilter" data-testid="filter-metric" placeholder="按指标编码筛选" />
        </label>
        <button class="btn" data-testid="query" type="submit">查询</button>
        <button class="btn ghost" type="button" @click="metricFilter = ''; reload()">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th>案件编号</th><th>指标编码</th><th>窗口标识</th><th>案件状态</th>
            <th>有效来源/来源总数</th><th>影响次数</th><th>失效原因</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredCases" :key="row.id" :data-status="row.案件状态" :class="{ 'row-invalid': row.案件状态 === '已失效' }">
            <td>{{ row.案件编号 }}</td>
            <td>{{ row.指标编码 }}</td>
            <td>{{ row.窗口标识 }}</td>
            <td><span class="status-badge" :class="badgeClass(row.案件状态)">{{ row.案件状态 }}</span></td>
            <td>{{ row.有效来源数 }} / {{ row.来源总数 }}</td>
            <td>{{ row.影响次数 }}<span class="muted-text">（上报 {{ row.上报总次数 }} 次）</span></td>
            <td>{{ row.失效原因 || '—' }}</td>
            <td class="row-actions">
              <button class="link" type="button" :data-testid="`open-case-${row.id}`" @click="openDetail(row.id)">
                查看案件详情
              </button>
            </td>
          </tr>
          <tr v-if="!filteredCases.length">
            <td colspan="8" class="empty-state">暂无案件，可从「指标异常检测」的已确认异常发起调查</td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- 案件详情 -->
    <template v-else>
      <CaseDetailPanel
        :case-id="selectedCase"
        @refresh="reload"
        @go-review="router.push('/conclusion_review/workbench')"
      />
    </template>

    <footer class="page-foot">
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { listCases, type AnomalyCase } from '@/api/case-workbench'
import CaseDetailPanel from '@/views/CaseDetailPanel.vue'

const router = useRouter()
const cases = ref<AnomalyCase[]>([])
const metricFilter = ref('')
const selectedCase = ref<number | null>(null)
const errorMessage = ref('')

const filteredCases = computed(() =>
  metricFilter.value
    ? cases.value.filter((c) => c.指标编码.toLowerCase().includes(metricFilter.value.toLowerCase()))
    : cases.value,
)
const reviewableCount = computed(() => cases.value.filter((c) => c.案件状态 === '可评审').length)
const invalidCount = computed(() => cases.value.filter((c) => c.案件状态 === '已失效').length)

function badgeClass(status: string): string {
  if (status === '已失效') return 'badge-invalid'
  if (status === '可评审' || status === '已评审') return 'badge-ok'
  return 'badge-progress'
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listCases({ size: '200' })
    cases.value = payload.items
    if (selectedCase.value !== null) {
      await openDetail(selectedCase.value)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '案件列表读取失败'
  }
}

async function openDetail(caseId: number) {
  selectedCase.value = caseId
}

function closeDetail() {
  selectedCase.value = null
}

onMounted(reload)
</script>
