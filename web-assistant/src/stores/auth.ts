import { defineStore } from 'pinia'
import { api } from '../api/client'

interface Session {
  token: string
  user: any
  tenant: any
  quota: any
}

// 会话标记（sessionStorage）：仅标识"本标签页已登录"，不含 token 本身；
// 真正的会话凭证为后端 HttpOnly Cookie（JS 不可读），token 不再持久化到 localStorage。
const SIGNED_KEY = 'rm_signed_in'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: '',
    user: null as any,
    tenant: null as any,
    quota: null as any,
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
  },
  actions: {
    setSession(r: Session) {
      this.token = r.token
      this.user = r.user
      this.tenant = r.tenant
      this.quota = r.quota
      sessionStorage.setItem(SIGNED_KEY, '1')
      // 清理历史遗留的 localStorage token（新会话走 HttpOnly Cookie）
      localStorage.removeItem('rm_token')
    },
    async login(email: string, password: string) {
      const r = await api.auth.login(email, password)
      this.setSession(r)
    },
    async register(payload: { company_name: string; name: string; email: string; password: string }) {
      const r = await api.auth.register(payload)
      this.setSession(r)
    },
    async fetchMe() {
      if (!this.token && !sessionStorage.getItem(SIGNED_KEY)) return
      try {
        const r = await api.auth.me()
        this.user = r.user
        this.tenant = r.tenant
        this.quota = r.quota
        this.token = 'cookie-session' // 会话有效标记（无 JWT 本体，凭证在 Cookie 中）
      } catch (e: any) {
        // 网络异常静默保留当前状态；401 已由 client 统一跳转，这里不产生 unhandled rejection
        console.warn('[auth] fetchMe failed:', e?.message || e)
      }
    },
    logout() {
      this.token = ''
      this.user = null
      this.tenant = null
      this.quota = null
      sessionStorage.removeItem(SIGNED_KEY)
      localStorage.removeItem('rm_token')
      // 清除后端 HttpOnly Cookie（尽力而为，失败不影响本地登出）
      api.auth.logout().catch(() => {})
    },
  },
})
