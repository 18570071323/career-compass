<template>
  <div class="company-watch-page">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      :title="disclaimer"
      class="disclaimer"
    />

    <el-card shadow="never" class="step-card">
      <template #header>
        <div class="card-title card-head">
          <span><el-icon><Warning /></el-icon> 公司避雷与推荐清单</span>
          <el-button size="small" plain @click="submitVisible = true">投稿共建</el-button>
        </div>
      </template>

      <el-tabs v-model="tab">
        <el-tab-pane label="⚠️ 避雷公司" name="blacklist">
          <el-table :data="blacklist" v-loading="loading" stripe>
            <el-table-column prop="company" label="公司" min-width="140" />
            <el-table-column prop="industry" label="行业" width="110" />
            <el-table-column label="风险等级" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.risk_level === '高' ? 'danger' : 'warning'" size="small">{{ row.risk_level || '中' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="避雷原因" min-width="320">
              <template #default="{ row }">
                <div class="reason">{{ row.reason }}</div>
                <div class="meta">
                  <el-tag v-if="row.source === 'user'" size="small" type="info">用户投稿</el-tag>
                  <a v-if="row.source_url" :href="row.source_url" target="_blank" rel="noopener" class="src-link">来源报道</a>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="🏆 高精尖企业推荐" name="recommended">
          <el-table :data="recommended" v-loading="loading" stripe>
            <el-table-column prop="company" label="公司" min-width="140" />
            <el-table-column prop="industry" label="领域" width="140" />
            <el-table-column label="推荐理由" min-width="380">
              <template #default="{ row }">
                <div class="reason">{{ row.reason }}</div>
                <div class="meta">
                  <el-tag v-if="row.source === 'user'" size="small" type="info">用户投稿</el-tag>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 投稿 -->
    <el-dialog v-model="submitVisible" title="投稿共建（应届生互助）" width="560px">
      <el-form label-width="90px">
        <el-form-item label="公司名称"><el-input v-model="form.company" placeholder="如：XX 科技" /></el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.kind">
            <el-radio value="blacklist">避雷</el-radio>
            <el-radio value="warning">预警（谨慎）</el-radio>
            <el-radio value="recommended">推荐</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="行业"><el-input v-model="form.industry" placeholder="如：互联网/制造业（选填）" /></el-form-item>
        <el-form-item v-if="form.kind !== 'recommended'" label="风险等级">
          <el-select v-model="form.risk_level" style="width: 100%">
            <el-option label="高（强烈建议避雷）" value="高" />
            <el-option label="中（谨慎投递）" value="中" />
          </el-select>
        </el-form-item>
        <el-form-item label="原因/理由">
          <el-input v-model="form.reason" type="textarea" :rows="3"
            placeholder="如：2026年X月要求应届生以个人原因离职 / 是XXX领域的龙头企业" />
        </el-form-item>
        <el-form-item label="来源链接">
          <el-input v-model="form.source_url" placeholder="报道/信息来源 URL（选填）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Warning } from '@element-plus/icons-vue'
import { api } from '../api/client'

const tab = ref('blacklist')
const disclaimer = ref('')
const blacklist = ref<any[]>([])
const recommended = ref<any[]>([])
const loading = ref(false)

const submitVisible = ref(false)
const submitting = ref(false)
const form = ref<any>({ company: '', kind: 'blacklist', industry: '', risk_level: '高', reason: '', source_url: '' })

async function load() {
  loading.value = true
  try {
    const [b, r] = await Promise.all([
      api.candidate.companies({ kind: 'blacklist', limit: 100 }),
      api.candidate.companies({ kind: 'recommended', limit: 100 }),
    ])
    blacklist.value = b.items || []
    recommended.value = r.items || []
    disclaimer.value = b.disclaimer || ''
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!form.value.company || form.value.reason.trim().length < 5) {
    ElMessage.warning('请填写公司名称与原因/理由（不少于 5 字）')
    return
  }
  const src = (form.value.source_url || '').trim()
  if (src && !/^https?:\/\//i.test(src)) {
    ElMessage.warning('来源链接仅支持 http/https 开头的网址')
    return
  }
  submitting.value = true
  try {
    const res = await api.candidate.submitCompany({
      company: form.value.company,
      kind: form.value.kind,
      industry: form.value.industry || null,
      risk_level: form.value.kind === 'recommended' ? null : form.value.risk_level,
      reason: form.value.reason,
      source_url: src || null,
    })
    ElMessage.success(res.note || '已收录，感谢共建')
    submitVisible.value = false
    form.value = { company: '', kind: 'blacklist', industry: '', risk_level: '高', reason: '', source_url: '' }
    load()
  } catch (e: any) {
    ElMessage.error(e.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.company-watch-page { display: flex; flex-direction: column; gap: 16px; }
.disclaimer { border-radius: 8px; }
.card-title { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.reason { line-height: 1.6; }
.meta { margin-top: 4px; display: flex; align-items: center; gap: 8px; }
.src-link { font-size: 12px; color: #409eff; text-decoration: none; }
</style>
