// 后端 API 客户端（开发环境经 Vite 代理到 http://127.0.0.1:8000）
const BASE = '/api/v1'
const TOKEN_KEY = 'rm_token'

// 401 会话过期回调（应用层注册：统一清 Pinia store + 跳登录页），避免 client 与 store 双数据源漂移
let unauthorizedHandler: (() => void) | null = null

export function setUnauthorizedHandler(fn: () => void) {
  unauthorizedHandler = fn
}

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function qs(params?: Record<string, unknown>): string {
  if (!params) return ''
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  })
  return sp.toString()
}

export function fd(data: Record<string, unknown>): FormData {
  const form = new FormData()
  Object.entries(data).forEach(([k, v]) => {
    if (v !== undefined && v !== null) form.append(k, v as any)
  })
  return form
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isForm = options.body instanceof FormData
  const headers: Record<string, string> = isForm ? {} : { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(BASE + path, { ...options, headers })
  // 白名单仅排除 login/register 的凭证错误 401；/auth/me 的 401 同样视为会话过期
  if (resp.status === 401 && path !== '/auth/login' && path !== '/auth/register') {
    if (unauthorizedHandler) {
      unauthorizedHandler() // 应用层：清 store + 跳登录页
    } else {
      setToken(null)
      if (!location.pathname.startsWith('/login')) location.href = '/login'
    }
    throw new Error('请先登录')
  }
  if (!resp.ok) {
    let detail: unknown = resp.statusText
    try {
      const j = await resp.json()
      detail = Array.isArray(j.detail)
        ? j.detail.map((d: any) => d.msg).join('；')
        : j.detail || j.message || JSON.stringify(j)
    } catch {
      /* 非 JSON 响应 */
    }
    throw new Error(String(detail))
  }
  return resp.json()
}

export const api = {
  health: () => fetch('/health').then((r) => r.json()),
  auth: {
    register: (body: { company_name: string; name: string; email: string; password: string }) =>
      request('/auth/register', { method: 'POST', body: JSON.stringify(body) }),
    login: (email: string, password: string) =>
      request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
    me: () => request('/auth/me'),
    logout: () => request('/auth/logout', { method: 'POST' }),
  },
  jobs: {
    list: (p?: Record<string, unknown>) => request(`/jobs?${qs(p)}`),
    create: (body: { title?: string; department?: string; jd_text: string }) =>
      request('/jobs', { method: 'POST', body: JSON.stringify(body) }),
    get: (id: string) => request(`/jobs/${id}`),
    update: (id: string, body: { status?: string; title?: string }) =>
      request(`/jobs/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    mine: (id: string) => request(`/jobs/${id}/mine-candidates`, { method: 'POST' }),
    candidateScores: (id: string) => request(`/jobs/${id}/candidate-scores`),
  },
  resumes: {
    list: (p?: Record<string, unknown>) => request(`/resumes?${qs(p)}`),
    get: (id: string) => request(`/resumes/${id}`),
    remove: (id: string) => request(`/resumes/${id}`, { method: 'DELETE' }),
    refresh: (id: string, jobId: string) =>
      request(`/resumes/${id}/refresh`, { method: 'POST', body: fd({ job_id: jobId }) }),
    matchJobs: (id: string) => request(`/resumes/${id}/match-open-jobs`, { method: 'POST' }),
  },
  analysis: {
    analyze: (form: FormData) => request('/analysis/analyze', { method: 'POST', body: form }),
    get: (id: string) => request(`/analysis/${id}`),
  },
  batch: {
    list: (p?: Record<string, unknown>) => request(`/batch-jobs?${qs(p)}`),
    create: (form: FormData) => request('/batch-jobs', { method: 'POST', body: form }),
    get: (id: string) => request(`/batch-jobs/${id}`),
    retryFailed: (id: string) => request(`/batch-jobs/${id}/retry-failed`, { method: 'POST' }),
    exportUrl: (id: string) => `${BASE}/batch-jobs/${id}/export`,
  },
  compare: {
    create: (body: { name?: string; job_id: string; resume_ids: string[] }) =>
      request('/compare-sets', { method: 'POST', body: JSON.stringify(body) }),
    list: () => request('/compare-sets'),
    get: (id: string) => request(`/compare-sets/${id}`),
    remove: (id: string) => request(`/compare-sets/${id}`, { method: 'DELETE' }),
    exportUrl: (id: string) => `${BASE}/compare-sets/${id}/export`,
  },
  settings: {
    getRefreshRule: () => request('/settings/refresh-rule'),
    updateRefreshRule: (body: Record<string, unknown>) =>
      request('/settings/refresh-rule', { method: 'PUT', body: JSON.stringify(body) }),
    runRefresh: () => request('/settings/refresh-rule/run', { method: 'POST' }),
  },
  hits: {
    list: (p?: Record<string, unknown>) => request(`/candidate-hits?${qs(p)}`),
    update: (id: string, status: string) =>
      request(`/candidate-hits/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
    exportUrl: (p?: Record<string, unknown>) => `${BASE}/candidate-hits/export?${qs(p)}`,
  },
  coze: {
    status: () => request('/coze/status'),
    connect: (body: { client_id: string; client_secret?: string; workspace_id?: string }) =>
      request('/coze/connect', { method: 'POST', body: JSON.stringify(body) }),
    authorizeUrl: () => request('/coze/authorize-url'),
    workflows: () => request('/coze/workflows'),
    bind: (workflowId: string) =>
      request('/coze/bind', { method: 'POST', body: JSON.stringify({ workflow_id: workflowId }) }),
    disconnect: () => request('/coze/disconnect', { method: 'POST' }),
  },
  billing: {
    plans: () => request('/billing/plans'),
    orders: () => request('/billing/orders'),
    createOrder: (plan: string, months: number) =>
      request('/billing/orders', { method: 'POST', body: JSON.stringify({ plan, months }) }),
    confirmOrder: (id: string) => request(`/billing/orders/${id}/confirm`, { method: 'POST' }),
    cancelOrder: (id: string) => request(`/billing/orders/${id}/cancel`, { method: 'POST' }),
  },
  mpAdmin: {
    users: (p?: Record<string, unknown>) => request(`/admin/mp/users?${qs(p)}`),
    grant: (body: { user_id: string; delta: number; reason?: string }) =>
      request('/admin/mp/grant', { method: 'POST', body: JSON.stringify(body) }),
    resetFree: (body: { user_id: string }) =>
      request('/admin/mp/reset-free', { method: 'POST', body: JSON.stringify(body) }),
    logs: (limit = 50) => request(`/admin/mp/logs?${qs({ limit })}`),
  },
  candidate: {
    recommend: (form: FormData) => request('/candidate/recommend', { method: 'POST', body: form }),
    score: (resumeId: string, jdId: string, weightTier = 'auto') =>
      request('/candidate/score', {
        method: 'POST',
        body: fd({ resume_id: resumeId, jd_id: jdId, weight_tier: weightTier }),
      }),
    directionMatch: (form: FormData) =>
      request('/candidate/direction-match', { method: 'POST', body: form }),
    directionScore: (resumeId: string, categoryId: string, weightTier = 'auto') =>
      request('/candidate/direction-score', {
        method: 'POST',
        body: fd({ resume_id: resumeId, category_id: categoryId, weight_tier: weightTier }),
      }),
    resumeAnalysis: (form: FormData) =>
      request('/candidate/resume-analysis', { method: 'POST', body: form }),
    resumeRewrite: (form: FormData) =>
      request('/candidate/resume-rewrite', { method: 'POST', body: form }),
    submitJd: (form: FormData) => request('/candidate/jd/submit', { method: 'POST', body: form }),
    crawlJd: (body: Record<string, unknown>) =>
      request('/candidate/jd/crawl', { method: 'POST', body: JSON.stringify(body) }),
    jdLibrary: (p?: Record<string, unknown>) => request(`/candidate/jd-library?${qs(p)}`),
    newCareers: (p?: Record<string, unknown>) => request(`/candidate/new-careers?${qs(p)}`),
    directionProfile: (name: string) => request(`/candidate/direction-profile?${qs({ name })}`),
    careerPlan: (body: Record<string, unknown>) =>
      request('/candidate/career-plan', { method: 'POST', body: JSON.stringify(body) }),
    categories: () => request('/candidate/categories'),
    jdDetail: (id: string) => request(`/candidate/jd/${id}`),
    companies: (p?: Record<string, unknown>) => request(`/candidate/companies?${qs(p)}`),
    submitCompany: (body: Record<string, unknown>) =>
      request('/candidate/companies', { method: 'POST', body: JSON.stringify(body) }),
  },
  calibration: {
    feedback: (body: Record<string, unknown>) =>
      request('/calibration/feedback', { method: 'POST', body: JSON.stringify(body) }),
    stats: (p?: Record<string, unknown>) => request(`/calibration/stats?${qs(p)}`),
    settings: () => request('/calibration/settings'),
    updateSettings: (body: Record<string, unknown>) =>
      request('/calibration/settings', { method: 'PUT', body: JSON.stringify(body) }),
    certs: () => request('/calibration/certs'),
    evalCases: () => request('/calibration/eval-cases'),
    createEvalCase: (body: Record<string, unknown>) =>
      request('/calibration/eval-cases', { method: 'POST', body: JSON.stringify(body) }),
    deleteEvalCase: (id: string) => request(`/calibration/eval-cases/${id}`, { method: 'DELETE' }),
    evalReport: () => request('/calibration/eval-report'),
    trainingData: () => request('/calibration/training-data'),
  },
}
