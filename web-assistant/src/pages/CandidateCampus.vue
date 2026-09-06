<template>
  <div class="candidate-page">
    <!-- 校招求职：上传简历 → 方向匹配 / 简历优化分析（无明确 JD 也能用） -->
    <el-card shadow="never" class="step-card">
      <template #header>
        <div class="card-title"><el-icon><School /></el-icon> 第一步：上传简历（校招场景可没有明确 JD）</div>
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
        <div class="action-row">
          <el-button :loading="dirMatching" :disabled="!file" @click="doDirectionMatch">
            <el-icon style="margin-right: 4px"><Compass /></el-icon>方向匹配（找方向）
          </el-button>
          <el-button :loading="analyzing" :disabled="!file" @click="doResumeAnalysis">
            <el-icon style="margin-right: 4px"><MagicStick /></el-icon>简历分析 + 优化建议
          </el-button>
          <el-button type="primary" :loading="rewriting" :disabled="!file" @click="doResumeRewrite">
            <el-icon style="margin-right: 4px"><DocumentCopy /></el-icon>生成优化版简历
          </el-button>
        </div>
        <div class="action-row target-row">
          <span class="target-label">优化目标（可选）：</span>
          <el-select v-model="targetCategory" placeholder="选择方向后，优化建议将更有针对性" clearable filterable style="width: 280px">
            <el-option v-for="c in directionOptions" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
          <span class="target-hint">不选择则做通用诊断</span>
        </div>
      </div>
    </el-card>

    <!-- 方向匹配结果 -->
    <Transition name="fade-slide">
    <el-card v-if="directions.length" shadow="never" class="step-card">
      <template #header>
        <div class="card-title"><el-icon><Compass /></el-icon> 你的简历适合的方向（按岗位库方向画像匹配）</div>
      </template>
      <el-table :data="directions" stripe>
        <el-table-column label="排名" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.rank === 1 ? 'danger' : 'info'" round>{{ row.rank }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="匹配度" width="90" align="center">
          <template #default="{ row }">
            <span :class="scoreClass(row.score)"><b>{{ row.score }}</b></span>
          </template>
        </el-table-column>
        <el-table-column label="方向" min-width="150">
          <template #default="{ row }">
            <div class="job-title">{{ row.name }}</div>
            <div class="job-meta">
              岗位库 {{ row.jd_count }} 条样本
              <el-tooltip
                v-if="row.low_barrier"
                :content="`该方向所需技能少（${row.skill_scope} 项），匹配分天然偏高：分数高不代表竞争小或发展空间好，请结合个人兴趣与城市综合判断`"
                placement="top"
              >
                <el-tag size="small" type="info" class="src-tag" style="cursor: help">低门槛·分易偏高</el-tag>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="方向核心技能（Top）" min-width="200">
          <template #default="{ row }">
            <el-tag v-for="s in row.core_skills.slice(0, 6)" :key="s" size="small" type="primary" class="tag">{{ s }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="已命中" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="s in row.hit_skills.slice(0, 5)" :key="s" size="small" type="success" class="tag">{{ s }}</el-tag>
            <span v-if="!row.hit_skills.length" class="muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="待补技能" min-width="150">
          <template #default="{ row }">
            <el-tag v-for="s in row.missing_skills.slice(0, 4)" :key="s" size="small" type="warning" class="tag">{{ s }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="理由" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.reason }}</template>
        </el-table-column>
        <el-table-column label="操作" width="132" align="center" fixed="right">
          <template #default="{ row }">
            <div class="op-col">
              <el-button size="small" type="primary" plain :loading="scoringCat === row.category_id" @click="doDirectionScore(row.category_id)">
                方向报告
              </el-button>
              <el-button size="small" plain :loading="optimizingCat === row.category_id" @click="optimizeForDirection(row)">
                按此方向优化
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    </Transition>

    <!-- 方向级五维报告 -->
    <Transition name="fade-slide">
    <el-card v-if="report" shadow="never" class="step-card">
      <template #header>
        <div class="card-title">
          <el-icon><DataAnalysis /></el-icon> 方向匹配报告 —— {{ report.jd.title }}
        </div>
      </template>
      <FiveDimReport :report="report" :tier="tier" @tier-change="onTierChange" />
    </el-card>
    </Transition>

    <!-- 简历优化分析 -->
    <Transition name="fade-slide">
    <el-card v-if="analysis" shadow="never" class="step-card">
      <template #header>
        <div class="card-title"><el-icon><MagicStick /></el-icon> 简历优化建议（{{ analysis.overall }}）</div>
      </template>

      <el-divider content-position="left">① 完整性检查</el-divider>
      <el-table :data="analysis.completeness" size="small" border>
        <el-table-column label="板块" min-width="220">
          <template #default="{ row }">{{ row.item }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.ok ? 'success' : 'danger'" size="small">{{ row.ok ? '完整' : '待补' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="260">
          <template #default="{ row }"><span :class="row.ok ? '' : 'warn-text'">{{ row.note || '—' }}</span></template>
        </el-table-column>
      </el-table>

      <el-divider content-position="left">② 五维优化建议（按匹配评分维度）</el-divider>
      <el-collapse>
        <el-collapse-item v-for="d in dimSuggestionRows" :key="d.key" :title="d.label">
          <ul class="sug-list">
            <li v-for="(s, i) in d.items" :key="i">{{ s }}</li>
          </ul>
        </el-collapse-item>
      </el-collapse>

      <el-divider content-position="left">③ 高性价比改动</el-divider>
      <ol class="sug-list">
        <li v-for="(s, i) in analysis.quick_wins" :key="i">{{ s }}</li>
      </ol>

      <el-divider content-position="left">④ 参考写法（动作-工具-量化）</el-divider>
      <el-alert
        v-for="(s, i) in analysis.example_lines"
        :key="i"
        :title="s"
        type="info"
        :closable="false"
        class="example-item"
      />

      <template v-if="hasRelevanceAdvice">
        <el-divider content-position="left">⑤ 经历详略建议（突出针对性）</el-divider>
        <div v-if="analysis.relevance_advice?.related?.length" class="rel-group">
          <div v-for="(r, i) in analysis.relevance_advice.related" :key="'rel' + i" class="rel-item">
            <el-tag type="success" size="small" class="rel-tag">详写</el-tag>
            <b>{{ r.name }}</b>
            <div class="rel-advice">{{ r.advice }}</div>
          </div>
        </div>
        <div v-if="analysis.relevance_advice?.unrelated?.length" class="rel-group">
          <div v-for="(r, i) in analysis.relevance_advice.unrelated" :key="'un' + i" class="rel-item">
            <el-tag type="info" size="small" class="rel-tag">精简</el-tag>
            <b>{{ r.name }}</b>
            <div class="rel-advice">{{ r.advice }}</div>
          </div>
        </div>
      </template>

      <el-divider v-if="analysis.risk_flags.length" content-position="left">⑥ 风险提示</el-divider>
      <el-alert v-for="(s, i) in analysis.risk_flags" :key="i" :title="s" type="warning" :closable="false" class="example-item" />
    </el-card>
    </Transition>

    <!-- 优化版简历：风格选择 + 预览 + 打印 -->
    <Transition name="fade-slide">
    <el-card v-if="rewrite" shadow="never" class="step-card">
      <template #header>
        <div class="card-title card-head">
          <span><el-icon><DocumentCopy /></el-icon> 优化版简历 —— 选择模板风格</span>
          <el-button type="primary" size="small" :icon="Printer" @click="printResume">打印 / 导出 PDF</el-button>
        </div>
      </template>
      <el-radio-group v-model="resumeStyle" class="style-picker">
        <el-radio-button value="modern">简约现代</el-radio-button>
        <el-radio-button value="classic">经典专业</el-radio-button>
        <el-radio-button value="creative">创意活力</el-radio-button>
        <el-radio-button value="tech">极客技术</el-radio-button>
      </el-radio-group>
      <div class="style-hint">
        已按优化建议改写内容（动作-工具-量化）；头像为姓名首字母占位，打印前可替换为证件照。
      </div>
      <el-alert
        v-if="rewrite.content.still_to_add?.length"
        title="以下内容原文缺失、建议手动补充（未写入正文，避免虚构）："
        type="info"
        :closable="false"
        class="mb8"
      >
        <ul class="sug-list">
          <li v-for="(s, i) in rewrite.content.still_to_add" :key="i">{{ s }}</li>
        </ul>
      </el-alert>
      <ResumePreview :content="rewrite.content" :style="resumeStyle" />
    </el-card>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Compass, DataAnalysis, DocumentCopy, MagicStick, Printer, School, UploadFilled } from '@element-plus/icons-vue'
import { api } from '../api/client'
import FiveDimReport from '../components/FiveDimReport.vue'
import ResumePreview from '../components/ResumePreview.vue'

const DIM_LABELS: Record<string, string> = {
  experience_match: '经验匹配度',
  skill_match: '技能匹配度',
  project_quality: '项目质量',
  differentiation: '差异化竞争力',
  growth_potential: '成长潜力',
}

const file = ref<File | null>(null)
// 请求序号：换文件/移除文件时自增，使在途旧请求回调失效（防异步竞态回填旧结果）
const reqSeq = ref(0)
// 动作级"最新令牌"：仅最新一次触发允许复位共享 loading，避免旧请求把新请求的 loading 关掉
let dirTicket = 0
let analysisTicket = 0
let rewriteTicket = 0
// 方向报告：行级加载标记（哪个方向在生成报告）+ 报告归属票据（last-clicked 生效）
const scoringCat = ref('')
let scoreTicket = 0
// 按此方向优化：行级加载标记
const optimizingCat = ref('')
const dirMatching = ref(false)
const analyzing = ref(false)
const rewriting = ref(false)
const resumeId = ref('')
const tier = ref('auto')
const directions = ref<any[]>([])
const report = ref<any>(null)
const analysis = ref<any>(null)
const rewrite = ref<any>(null)
const resumeStyle = ref('modern')
// 优化目标（针对性建议）：方向画像
const targetCategory = ref('')
const directionOptions = ref<any[]>([])

async function loadDirectionOptions() {
  try {
    const res = await api.candidate.categories()
    const flat: any[] = []
    ;(res.functions || []).forEach((f: any) => f.children.forEach((c: any) => flat.push(c)))
    directionOptions.value = flat
  } catch {
    ElMessage.warning('方向选项加载失败，请刷新重试')
  }
}
loadDirectionOptions()

const dimSuggestionRows = computed(() =>
  Object.entries(analysis.value?.dimension_suggestions || {}).map(([key, items]) => ({
    key,
    label: DIM_LABELS[key] || key,
    items: items as string[],
  })),
)

const hasRelevanceAdvice = computed(() => {
  const ra = analysis.value?.relevance_advice
  return !!(ra && (ra.related?.length || ra.unrelated?.length))
})

function clearDerived() {
  directions.value = []
  report.value = null
  analysis.value = null
  rewrite.value = null
  resumeId.value = ''
  scoringCat.value = ''
  optimizingCat.value = ''
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

async function doDirectionMatch() {
  if (!file.value) return
  const snap = reqSeq.value
  const t = ++dirTicket
  dirMatching.value = true
  try {
    const form = new FormData()
    form.append('file', file.value)
    form.append('top_n', '6')
    const res = await api.candidate.directionMatch(form)
    if (t !== dirTicket || snap !== reqSeq.value) return // 已被更新触发/换文件，丢弃旧结果
    resumeId.value = res.resume_id
    directions.value = res.items || []
    report.value = null
    if (!directions.value.length) ElMessage.warning('岗位库暂无方向样本，请先扩充岗位库')
  } catch (e: any) {
    if (t === dirTicket && snap === reqSeq.value) ElMessage.error(e.message || '方向匹配失败')
  } finally {
    if (t === dirTicket) dirMatching.value = false
  }
}

async function doDirectionScore(categoryId: string) {
  if (!resumeId.value) return
  const snap = reqSeq.value
  const ticket = ++scoreTicket // 使更早的方向报告失效（last-clicked 生效）
  scoringCat.value = categoryId
  try {
    const res = await api.candidate.directionScore(resumeId.value, categoryId, tier.value)
    if (ticket === scoreTicket && snap === reqSeq.value) report.value = res
  } catch (e: any) {
    if (ticket === scoreTicket && snap === reqSeq.value) ElMessage.error(e.message || '方向报告失败')
  } finally {
    if (scoringCat.value === categoryId) scoringCat.value = '' // 无条件复位本行 loading
  }
}

async function onTierChange(val: string) {
  tier.value = val
  if (!report.value) return
  const snap = reqSeq.value
  const ticket = ++scoreTicket
  scoringCat.value = '__tier__'
  try {
    const res = await api.candidate.directionScore(resumeId.value, report.value.category_id, val)
    if (ticket === scoreTicket && snap === reqSeq.value) report.value = res
  } catch (e: any) {
    if (ticket === scoreTicket && snap === reqSeq.value) ElMessage.error(e.message || '重新评分失败')
  } finally {
    if (scoringCat.value === '__tier__') scoringCat.value = ''
  }
}

async function doResumeAnalysis() {
  if (!file.value) return
  const snap = reqSeq.value
  const t = ++analysisTicket
  analyzing.value = true
  try {
    const form = new FormData()
    form.append('file', file.value)
    if (targetCategory.value) form.append('category_id', targetCategory.value)
    const res = await api.candidate.resumeAnalysis(form)
    if (t !== analysisTicket || snap !== reqSeq.value) return
    analysis.value = res.analysis
    if (!analysis.value?.completeness?.length) ElMessage.warning('未能生成分析，请稍后重试')
  } catch (e: any) {
    if (t === analysisTicket && snap === reqSeq.value) ElMessage.error(e.message || '分析失败')
  } finally {
    if (t === analysisTicket) {
      analyzing.value = false
      optimizingCat.value = ''
    }
  }
}

// 方向匹配结果 → 按该方向针对性优化
async function optimizeForDirection(row: any) {
  if (!file.value) return
  optimizingCat.value = row.category_id
  analyzing.value = true
  targetCategory.value = row.category_id
  await doResumeAnalysis()
}

async function doResumeRewrite() {
  if (!file.value) return
  const snap = reqSeq.value
  const t = ++rewriteTicket
  rewriting.value = true
  try {
    const form = new FormData()
    form.append('file', file.value)
    const res = await api.candidate.resumeRewrite(form)
    if (t !== rewriteTicket || snap !== reqSeq.value) return
    rewrite.value = res
    if (!res.content?.personal) ElMessage.warning('未能生成优化版简历，请稍后重试')
  } catch (e: any) {
    if (t === rewriteTicket && snap === reqSeq.value) ElMessage.error(e.message || '生成失败')
  } finally {
    if (t === rewriteTicket) rewriting.value = false
  }
}

function printResume() {
  window.print()
}

function scoreClass(score: number) {
  if (score >= 70) return 'score-good'
  if (score >= 55) return 'score-mid'
  return 'score-low'
}
</script>

<style scoped>
.candidate-page { display: flex; flex-direction: column; gap: 16px; }
.step-card { border-radius: 8px; }
.card-title { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.uploader { width: 100%; }
.actions { margin-top: 14px; display: flex; flex-direction: column; gap: 12px; }
.action-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.target-row { background: #fafbfd; border: 1px dashed #e4e7ed; border-radius: 8px; padding: 10px 14px; }
.target-label { color: #606266; font-size: 13px; font-weight: 500; flex: none; }
.target-hint { color: #c0c4cc; font-size: 12px; }
.job-title { font-weight: 600; color: #1f2d3d; }
.job-meta { font-size: 12px; color: #909399; margin-top: 2px; }
.tag { margin: 2px 4px 2px 0; }
.src-tag { margin-left: 6px; vertical-align: middle; }
.muted { color: #c0c4cc; font-size: 12px; }
.score-good { color: #67c23a; }
.score-mid { color: #e6a23c; }
.score-low { color: #f56c6c; }
.warn-text { color: #e6a23c; }
.sug-list { margin: 4px 0; padding-left: 20px; }
.sug-list li { margin: 6px 0; line-height: 1.6; }
.op-col { display: flex; flex-direction: column; gap: 6px; align-items: stretch; }
.op-col .el-button { margin-left: 0; width: 100%; }
.example-item { margin-bottom: 8px; }
.style-picker { margin-bottom: 10px; }
.style-hint { color: #909399; font-size: 12px; margin-bottom: 12px; }
.mb8 { margin-bottom: 10px; }
.rel-group { margin-bottom: 10px; }
.rel-item { margin-bottom: 10px; line-height: 1.6; }
.rel-tag { margin-right: 6px; }
.rel-advice { color: #606266; font-size: 12.5px; margin-top: 3px; padding-left: 4px; }
</style>
