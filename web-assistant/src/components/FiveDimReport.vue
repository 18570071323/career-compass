<template>
  <div v-if="report">
    <div class="report-toolbar">
      <span class="label">权重档位：</span>
      <el-radio-group :model-value="tier" @change="onTierChange">
        <el-radio-button value="auto">自动（推荐）</el-radio-button>
        <el-radio-button value="default">默认·综合</el-radio-button>
        <el-radio-button value="bigtech">大厂·高竞争</el-radio-button>
        <el-radio-button value="state">国企·传统行业</el-radio-button>
      </el-radio-group>
      <el-tag class="total-tag" :type="levelType" size="large">
        总分 {{ report.score.total_score }} · {{ report.score.level }}
      </el-tag>
    </div>

    <el-row :gutter="16">
      <el-col :span="10">
        <RadarChart :radar="radarData" />
      </el-col>
      <el-col :span="14">
        <el-table :data="dimRows" size="small" border>
          <el-table-column prop="label" label="维度" width="130" />
          <el-table-column label="得分" width="150">
            <template #default="{ row }">
              <b>{{ row.score }}</b> / {{ row.max }}
            </template>
          </el-table-column>
          <el-table-column label="分项拆解">
            <template #default="{ row }">
              <span v-for="(v, k) in row.breakdown" :key="k" class="bd-item">{{ k }} {{ v }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="doubts" v-if="report.score.doubts.length">
          <el-alert v-for="(d, i) in report.score.doubts" :key="i" type="warning" :closable="false" :title="`疑点：${d}`" class="doubt-item" />
        </div>
      </el-col>
    </el-row>

    <el-divider content-position="left">完整分析报告</el-divider>
    <ReportViewer :markdown="report.report_md" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import RadarChart from './RadarChart.vue'
import ReportViewer from './ReportViewer.vue'

interface DimBreakdown {
  [key: string]: number
}
interface DimRow {
  label: string
  score: number
  max: number
  breakdown: DimBreakdown
}
interface ScorePayload {
  total_score: number
  level: string
  tier: string
  doubts: string[]
  dimensions: Record<string, DimRow>
}
interface ReportPayload {
  score: ScorePayload
  report_md: string
}

const props = defineProps<{ report: ReportPayload | null; tier: string }>()
const emit = defineEmits<{ (e: 'tier-change', val: string): void }>()

function onTierChange(val: string) {
  emit('tier-change', val)
}

const radarData = computed(() => {
  const dims = props.report?.score?.dimensions
  if (!dims) return null
  const indicators: { name: string; max: number }[] = []
  const values: number[] = []
  Object.values(dims).forEach((d) => {
    indicators.push({ name: d.label, max: 100 })
    values.push(Math.round((d.score / (d.max || 1)) * 1000) / 10)
  })
  return { indicators, series: [{ name: '我的匹配', value: values }] }
})

const dimRows = computed(() => Object.values(props.report?.score?.dimensions || {}))

const levelType = computed(() => {
  const lv = props.report?.score?.level || ''
  if (lv.startsWith('S')) return 'success'
  if (lv.startsWith('A')) return 'primary'
  if (lv.startsWith('B')) return 'warning'
  return 'danger'
})
</script>

<style scoped>
.report-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.report-toolbar .label { color: #606266; }
.total-tag { margin-left: auto; font-weight: 700; }
.bd-item { display: inline-block; background: #f0f6ff; color: #409eff; border-radius: 4px; padding: 1px 8px; margin: 2px 4px 2px 0; font-size: 12px; }
.doubts { margin-top: 10px; }
.doubt-item { margin-bottom: 6px; }
</style>
