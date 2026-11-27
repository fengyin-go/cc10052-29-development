import { createRouter, createWebHistory } from 'vue-router'

import CaseWorkbench from '@/views/CaseWorkbench.vue'
import Overview from '@/views/Overview.vue'
import ReviewWorkbench from '@/views/ReviewWorkbench.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 专用工作台需在通用 :moduleKey 之前注册，避免被动态路由抢先匹配。
    { path: '/anomaly_case', name: 'anomaly-case-workbench', component: CaseWorkbench },
    { path: '/conclusion_review/workbench', name: 'review-workbench', component: ReviewWorkbench },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
