<template>
  <div class="candidate-page">
    <!-- 社招求职：上传简历 → 岗位匹配（有明确 JD）→ 五维报告 -->
    <el-card shadow="never" class="step-card">
      <template #header>
        <div class="card-title card-head">
          <span><el-icon><Briefcase /></el-icon> 第一步：上传简历，匹配社招岗位（需有明确 JD）</span>
          <div class="head-actions">
            <el-button size="small" @click="crawlVisible = true">
              <el-icon style="margin-right: 4px"><Download /></el-icon>扩充岗位库
            </el-button>
            <el-button size="small" plain @click="submitVisible = true">收录岗位</el-button>
          </div>
        </div>
      </template>
      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        :on-change="onFileChange"
        :on-remove="onFileRemove"
        :on-exceed="handleExceed"
        accept=".pdf,.doc,.docx,.txt,.png,.jpg,.jpeg,.webp,.bmp"
        class="uploader"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽简历到这里，或 <em>点击选择文件</em>（pdf/doc/docx/txt，扫描件/截图可传 png/jpg）</div>
      </el-upload>
      <div class="actions">
        <el-input v-model="preferCity" placeholder="期望城市（如：长沙）" clearable style="width: 200px" />
        <el-button type="primary" :loading="recommending" :disabled="!file" @click="doRecommend">
          开始岗位匹配
        </el-button>
      </div>
    </el-card>

    <!-- 推荐岗位 -->
    <Transition name="fade-slide">
    <el-card v-if="recommendations.length" shadow="never" class="step-card">
      <template #header>
        <div class="card-title"><el-icon><Trophy /></el-icon> 为你推荐的社招岗位（{{ recommendations.length }} 个）</div>
      </template>
      <el-table :data="recommendations" stripe>
        <el-table-column label="排名" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.rank === 1 ? 'danger' : 'info'" round>{{ row.rank }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="匹配度" width="90" align="center">
          <template #default="{ row }">
            <span :class="scoreClass(row.match_score)"><b>{{ row.match_score }}</b></span>
          </template>
        </el-table-column>
        <el-table-column label="岗位" min-width="220">
          <template #default="{ row }">
            <div class="job-title">
              {{ row.jd.title }}
              <el-tag v-if="row.risk_flag" size="small" type="danger" class="src-tag">⚠️ 避雷</el-tag>
              <el-tag v-if="row.jd.stability === 'bank'" size="small" type="primary" class="src-tag">🏦 银行</el-tag>
              <el-tag v-else-if="row.jd.stability === 'soe'" size="small" type="warning" class="src-tag">🏢 央国企</el-tag>
              <el-tag v-if="row.jd.source === 'crawler'" size="small" type="warning" class="src-tag">抓取</el-tag>
              <el-tag v-else-if="row.jd.source === 'user_submit'" size="small" type="info" class="src-tag">投稿</el-tag>
            </div>
            <div class="job-meta">
              {{ row.jd.company }} · {{ row.jd.category }} · {{ row.jd.city || '城市不限' }} · {{ row.jd.salary_range || '' }}
              <el-tag v-if="row.city_match" size="small" type="success" class="src-tag">同城</el-tag>
            </div>
            <div v-if="row.jd.exam_note" class="exam-note">📌 {{ row.jd.exam_note }}</div>
          </template>
        </el-table-column>
        <el-table-column label="命中技能" min-width="180">
          <template #default="{ row }">
            <el-tag v-for="s in row.hit_skills.slice(0, 6)" :key="s" size="small" type="success" class="tag">{{ s }}</el-tag>
            <span v-if="!row.hit_skills.length" class="muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="待补技能" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="s in row.missing_skills.slice(0, 5)" :key="s" size="small" type="warning" class="tag">{{ s }}</el-tag>
            <span v-if="!row.missing_skills.length" class="muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="理由" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.reason }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain :loading="scoringJd === row.jd.jd_id" @click="doScore(row.jd.jd_id)">
              五维报告
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    </Transition>

    <!-- 五维报告 -->
    <Transition name="fade-slide">
    <el-card v-if="report" shadow="never" class="step-card">
      <template #header>
        <div class="card-title">
          <el-icon><DataAnalysis /></el-icon> 五维匹配报告 —— {{ report.jd.title }} @ {{ report.jd.company }}
        </div>
      </template>
      <FiveDimReport :report="report" :tier="tier" @tier-change="onTierChange" />
    </el-card>
    </Transition>

    <!-- 反馈：评分校准 -->
    <Transition name="fade-slide">
    <el-card v-if="report" shadow="never" class="step-card">
      <template #header>
        <div class="card-title"><el-icon><ChatDotRound /></el-icon> 这个评分准吗？（反馈将用于持续校准模型）</div>
      </template>
      <div class="fb-dims">
        <div v-for="d in dimRows" :key="d.label" class="fb-dim">
          <span class="fb-label">{{ d.label }}</span>
          <el-radio-group :model-value="fbMap[d.label]" size="small" @change="(v: string) => (fbMap[d.label] = v)">
            <el-radio-button value="ok">准确</el-radio-button>
            <el-radio-button value="over">高估了</el-radio-button>
            <el-radio-button value="under">低估了</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <el-input v-model="fbComment" type="textarea" :rows="2" placeholder="补充说明（选填），如：项目复杂度应该更高、缺了 XX 证书等" class="mb8" />
      <div class="fb-actions">
        <el-button type="primary" plain :loading="fbSubmitting" @click="submitFeedback">提交反馈</el-button>
      </div>
    </el-card>
    </Transition>

    <!-- 扩充岗位库：crawl4ai 抓取 -->
    <el-dialog v-model="crawlVisible" title="扩充岗位库（抓取公开招聘页）" width="560px">
      <el-alert type="info" :closable="false" class="mb8"
        title="抓取的岗位会自动进入岗位库，参与简历推荐与方向匹配；请仅抓取允许公开访问的招聘页并控制频率。" />
      <el-form label-width="90px">
        <el-form-item label="招聘页 URL">
          <el-input v-model="crawlForm.urls" type="textarea" :rows="3"
            placeholder="每行一个列表页 URL，如：https://jobs.lever.co/leverdemo" />
        </el-form-item>
        <el-form-item label="站点适配">
          <el-select v-model="crawlForm.mode" style="width: 100%">
            <el-option label="通用（CSS schema / Markdown 解析）" value="default" />
            <el-option label="Lever ATS 招聘页" value="lever" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量上限">
          <el-input-number v-model="crawlForm.limit" :min="1" :max="20" />
          <span class="hint">每页最多抓取岗位数（抓取较慢，建议 5-10）</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="crawlVisible = false">取消</el-button>
        <el-button type="primary" :loading="crawling" @click="doCrawl">开始抓取</el-button>
      </template>
    </el-dialog>

    <!-- 收录岗位 -->
    <el-dialog v-model="submitVisible" title="收录岗位（共建岗位库）" width="560px">
      <el-form label-width="90px">
        <el-form-item label="公司"><el-input v-model="jdForm.company" placeholder="公司/组织名称" /></el-form-item>
        <el-form-item label="岗位名称"><el-input v-model="jdForm.title" placeholder="如：数据分析师" /></el-form-item>
        <el-form-item label="城市"><el-input v-model="jdForm.city" placeholder="如：北京（选填）" /></el-form-item>
        <el-form-item label="学历要求">
          <el-select v-model="jdForm.education" clearable style="width: 100%">
            <el-option v-for="e in ['本科及以上', '硕士及以上', '大专及以上', '不限']" :key="e" :label="e" :value="e" />
          </el-select>
        </el-form-item>
        <el-form-item label="行业">
          <el-select v-model="jdForm.industry" clearable style="width: 100%">
            <el-option v-for="i in industries" :key="i.id" :label="i.name" :value="i.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="岗位类别">
          <el-select v-model="jdForm.category" clearable style="width: 100%">
            <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="JD 文本">
          <el-input v-model="jdForm.jd_text" type="textarea" :rows="6" placeholder="粘贴岗位 JD：职责 + 任职要求（含技能）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" :loading="jdSubmitting" @click="submitJd">提交收录</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Briefcase, ChatDotRound, DataAnalysis, Download, Trophy, UploadFilled } from '@element-plus/icons-vue'
import { api } from '../api/client'
import FiveDimReport from '../components/FiveDimReport.vue'

const file = ref<File | null>(null)
// 请求序号：换文件/移除文件时自增，使在途旧请求回调失效（防异步竞态回填旧结果）
const reqSeq = ref(0)
// 五维报告：行级加载标记（正在评分的 jd_id）+ 报告归属票据（last-clicked 生效）
const scoringJd = ref('')
let scoreTicket = 0
const recommending = ref(false)
const resumeId = ref('')
const tier = ref('auto')
const preferCity = ref('')
const recommendations = ref<any[]>([])
const report = ref<any>(null)

const fbMap = ref<Record<string, string>>({})
const fbComment = ref('')
const fbSubmitting = ref(false)

const submitVisible = ref(false)
const jdSubmitting = ref(false)
const jdForm = ref<any>({ company: '', title: '', city: '', education: '', industry: '', category: '', jd_text: '' })
const industries = ref<any[]>([])
const categories = ref<any[]>([])

// 扩充岗位库（crawl4ai 抓取）
const crawlVisible = ref(false)
const crawling = ref(false)
const crawlForm = ref<any>({ urls: '', mode: 'lever', limit: 5 })

const dimRows = computed(() => Object.values(report.value?.score?.dimensions || {}))

async function loadCategories() {
  try {
    const res = await api.candidate.categories()
    industries.value = res.industries || []
    const flat: any[] = []
    ;(res.functions || []).forEach((f: any) => f.children.forEach((c: any) => flat.push(c)))
    categories.value = flat
  } catch {
    ElMessage.warning('岗位分类加载失败，请刷新重试')
  }
}

function clearDerived() {
  recommendations.value = []
  report.value = null
  resumeId.value = ''
  scoringJd.value = ''
}
function onFileChange(uploadFile: any) {
  if (uploadFile.raw) {
    reqSeq.value++ // 使在途旧请求失效
    file.value = uploadFile.raw
    clearDerived()
  }
}
function onFileRemove() {
  reqSeq.value++
  file.value = null
  clearDerived()
}
function handleExceed() {
  // limit=1 下选择新文件不会触发 on-change，需明确提示，避免静默使用旧简历
  ElMessage.warning('已选择一份简历，请先点击移除当前文件，再选择新简历')
}

async function doRecommend() {
  if (!file.value) return
  const snap = reqSeq.value
  recommending.value = true
  try {
    const form = new FormData()
    form.append('file', file.value)
    form.append('top_n', '10')
    if (preferCity.value.trim()) form.append('city', preferCity.value.trim())
    const res = await api.candidate.recommend(form)
    if (snap !== reqSeq.value) return // 期间已换/移文件，丢弃旧结果
    resumeId.value = res.resume_id
    recommendations.value = res.items || []
    if (res.prefer_city_auto && !preferCity.value) {
      preferCity.value = res.prefer_city_auto
      // 自动回填发生在本次响应后，当前结果未按该城市计算，明确提示用户
      ElMessage.info(`已按简历期望城市「${res.prefer_city_auto}」自动填入；再次点击匹配可查看同城优先结果`)
    }
    report.value = null
    if (!recommendations.value.length) ElMessage.warning('暂未匹配到合适岗位，可稍后扩充岗位库再试')
  } catch (e: any) {
    if (snap === reqSeq.value) ElMessage.error(e.message || '匹配失败')
  } finally {
    recommending.value = false
  }
}

async function doScore(jdId: string) {
  if (!resumeId.value) return
  const snap = reqSeq.value
  const ticket = ++scoreTicket // 使更早的评分失效（last-clicked 生效）
  scoringJd.value = jdId
  try {
    const res = await api.candidate.score(resumeId.value, jdId, tier.value)
    if (ticket === scoreTicket && snap === reqSeq.value) report.value = res
  } catch (e: any) {
    if (ticket === scoreTicket && snap === reqSeq.value) ElMessage.error(e.message || '评分失败')
  } finally {
    if (scoringJd.value === jdId) scoringJd.value = '' // 无条件复位本行 loading
  }
}

async function onTierChange(val: string) {
  tier.value = val
  if (!report.value) return
  const snap = reqSeq.value
  const ticket = ++scoreTicket
  scoringJd.value = '__tier__'
  try {
    const res = await api.candidate.score(resumeId.value, report.value.jd.jd_id, val)
    if (ticket === scoreTicket && snap === reqSeq.value) report.value = res
  } catch (e: any) {
    if (ticket === scoreTicket && snap === reqSeq.value) ElMessage.error(e.message || '重新评分失败')
  } finally {
    if (scoringJd.value === '__tier__') scoringJd.value = ''
  }
}

function scoreClass(score: number) {
  if (score >= 70) return 'score-good'
  if (score >= 55) return 'score-mid'
  return 'score-low'
}

async function submitFeedback() {
  const marked = Object.entries(fbMap.value).filter(([, v]) => v)
  if (!marked.length) {
    ElMessage.warning('请至少标注一个维度')
    return
  }
  const over = marked.filter(([, v]) => v === 'over').map(([k]) => k)
  const under = marked.filter(([, v]) => v === 'under').map(([k]) => k)
  const ok = marked.filter(([, v]) => v === 'ok').map(([k]) => k)
  fbSubmitting.value = true
  try {
    await api.calibration.feedback({
      target_type: 'recommendation',
      resume_id: resumeId.value,
      jd_id: report.value.jd.jd_id,
      role: 'candidate',
      dim_overrated: over,
      dim_underrated: under,
      dim_ok: ok,
      comment: fbComment.value || null,
    })
    ElMessage.success('感谢反馈，已用于模型校准')
    fbMap.value = {}
    fbComment.value = ''
  } catch (e: any) {
    ElMessage.error(e.message || '提交失败')
  } finally {
    fbSubmitting.value = false
  }
}

async function submitJd() {
  if (!jdForm.value.company || !jdForm.value.title || jdForm.value.jd_text.trim().length < 30) {
    ElMessage.warning('请填写公司、岗位名称，JD 文本不少于 30 字')
    return
  }
  jdSubmitting.value = true
  try {
    const form = new FormData()
    Object.entries(jdForm.value).forEach(([k, v]) => {
      if (v) form.append(k, v as string)
    })
    const res = await api.candidate.submitJd(form)
    ElMessage.success(`已收录：${res.title} @ ${res.company}（技能 ${(res.skills || []).length} 项）`)
    submitVisible.value = false
    jdForm.value = { company: '', title: '', city: '', education: '', industry: '', category: '', jd_text: '' }
  } catch (e: any) {
    ElMessage.error(e.message || '收录失败')
  } finally {
    jdSubmitting.value = false
  }
}

async function doCrawl() {
  const urls = crawlForm.value.urls.split('\n').map((s: string) => s.trim()).filter(Boolean)
  if (!urls.length) {
    ElMessage.warning('请填写招聘页 URL')
    return
  }
  crawling.value = true
  try {
    const res = await api.candidate.crawlJd({
      urls,
      mode: crawlForm.value.mode,
      limit: crawlForm.value.limit,
    })
    ElMessage.success(`抓取完成：发现 ${res.listed} 个岗位，入库 ${res.saved} 条（失败 ${res.failed}），岗位库共 ${res.total_jd} 条`)
    crawlVisible.value = false
    crawlForm.value = { urls: '', mode: 'lever', limit: 5 }
  } catch (e: any) {
    ElMessage.error(e.message || '抓取失败')
  } finally {
    crawling.value = false
  }
}

loadCategories()
</script>

<style scoped>
.candidate-page { display: flex; flex-direction: column; gap: 16px; }
.step-card { border-radius: 8px; }
.card-title { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.head-actions { display: flex; align-items: center; gap: 8px; }
.src-tag { margin-left: 6px; }
.mb8 { margin-bottom: 10px; }
.hint { color: #909399; font-size: 12px; margin-left: 8px; }
.uploader { width: 100%; }
.actions { margin-top: 14px; text-align: center; }
.job-title { font-weight: 600; color: #1f2d3d; }
.job-meta { font-size: 12px; color: #909399; margin-top: 2px; }
.exam-note { font-size: 12px; color: #b7791f; background: #fdf6ec; border-radius: 4px; padding: 2px 8px; margin-top: 4px; display: inline-block; }
.tag { margin: 2px 4px 2px 0; }
.muted { color: #c0c4cc; font-size: 12px; }
.score-good { color: #67c23a; }
.score-mid { color: #e6a23c; }
.score-low { color: #f56c6c; }
.fb-dims { display: flex; flex-wrap: wrap; gap: 8px 24px; margin-bottom: 12px; }
.fb-dim { display: flex; align-items: center; gap: 10px; }
.fb-label { width: 110px; color: #606266; font-size: 13px; }
.mb8 { margin-bottom: 10px; }
.fb-actions { text-align: right; }
</style>
