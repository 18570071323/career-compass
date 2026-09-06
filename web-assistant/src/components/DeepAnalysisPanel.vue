<template>
  <div v-if="data" class="deep-panel">
    <!-- 总体评估 -->
    <div class="section">
      <div class="section-title">总体评估</div>
      <p class="overall">{{ data.overall_assessment }}</p>
    </div>

    <!-- 项目含金量 -->
    <div class="section">
      <div class="section-title">项目含金量分析</div>
      <el-collapse v-if="data.project_analysis?.length">
        <el-collapse-item v-for="(p, i) in data.project_analysis" :key="i">
          <template #title>
            <span class="proj-name">{{ p.name }}</span>
            <el-tag size="small" :type="depthTag(p.role_depth)" class="ml">{{ p.role_depth }}</el-tag>
            <el-tag size="small" :type="complexTag(p.complexity)" class="ml">{{ p.complexity }}</el-tag>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="业务规模">{{ p.business_scale || '未说明' }}</el-descriptions-item>
            <el-descriptions-item label="技术深度">{{ p.tech_depth }}</el-descriptions-item>
          </el-descriptions>
          <div v-if="p.authenticity_signals?.length" class="sub-block">
            <div class="sub-label">真实性信号</div>
            <el-tag v-for="(s, j) in p.authenticity_signals" :key="j" type="success" class="mb-tag">{{ s }}</el-tag>
          </div>
          <div v-if="p.concerns?.length" class="sub-block">
            <div class="sub-label">疑点 / 待验证</div>
            <el-tag v-for="(c, j) in p.concerns" :key="j" type="warning" class="mb-tag">{{ c }}</el-tag>
          </div>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-else description="暂无项目数据" :image-size="50" />
    </div>

    <!-- 风险点 -->
    <div v-if="data.risk_flags?.length" class="section">
      <div class="section-title">风险提示</div>
      <div v-for="(rf, i) in data.risk_flags" :key="i" class="risk-item">⚠️ {{ rf }}</div>
    </div>

    <!-- 面试问题 -->
    <div class="section">
      <div class="section-title-row">
        <span class="section-title">面试问询建议</span>
        <el-button link type="primary" size="small" @click="copyQuestions">复制问题清单</el-button>
      </div>
      <div v-for="(q, i) in data.interview_questions || []" :key="i" class="question-card">
        <div class="q-index">{{ i + 1 }}</div>
        <div>
          <div class="q-text">{{ q.question }}</div>
          <div class="q-meta">
            <el-tag size="small" type="primary">{{ q.purpose }}</el-tag>
            <span class="q-target">{{ q.target }}</span>
          </div>
        </div>
      </div>
      <el-empty v-if="!(data.interview_questions || []).length" description="暂无面试问题" :image-size="50" />
    </div>
  </div>
  <el-empty v-else description="该次分析未生成深度评估（演示模式或无数据）" />
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'

const props = defineProps<{ data: any }>()

function depthTag(v: string) {
  if (v === '主导者') return 'danger'
  if (v === '核心参与者') return 'warning'
  if (v === '一般参与者') return 'info'
  return 'info'
}
function complexTag(v: string) {
  if (v === '高') return 'danger'
  if (v === '中') return 'warning'
  return 'info'
}

function copyQuestions() {
  const qs = props.data?.interview_questions || []
  const text = qs.map((q: any, i: number) => `${i + 1}. ${q.question}\n   （目的：${q.purpose}｜针对：${q.target || '-'}）`).join('\n\n')
  if (!text) return
  navigator.clipboard?.writeText(text).then(
    () => ElMessage.success('面试问题已复制'),
    () => ElMessage.warning('复制失败，请手动选择复制'),
  )
}
</script>

<style scoped>
.section { margin-bottom: 18px; }
.section-title { font-weight: 600; color: #303133; margin-bottom: 8px; display: inline-block; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; }
.overall { color: #606266; line-height: 1.7; font-size: 13px; }
.proj-name { font-weight: 600; margin-right: 8px; }
.ml { margin-left: 6px; }
.sub-block { margin-top: 10px; }
.sub-label { font-size: 12px; color: #909399; margin-bottom: 6px; }
.mb-tag { margin: 0 6px 6px 0; white-space: normal; height: auto; }
.risk-item { background: #fef0f0; color: #f56c6c; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px; font-size: 13px; }
.question-card { display: flex; gap: 10px; border: 1px solid #ebeef5; border-radius: 8px; padding: 12px; margin-bottom: 10px; }
.q-index { width: 22px; height: 22px; border-radius: 50%; background: #409EFF; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 12px; flex-shrink: 0; }
.q-text { font-size: 13px; color: #303133; line-height: 1.6; }
.q-meta { margin-top: 6px; display: flex; align-items: center; gap: 8px; }
.q-target { font-size: 12px; color: #909399; }
</style>
