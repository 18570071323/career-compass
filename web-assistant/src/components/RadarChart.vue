<template>
  <div ref="el" class="radar-chart" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

interface RadarSeries {
  name: string
  value: number[]
}
interface RadarData {
  indicators?: { name: string; max: number }[]
  series?: RadarSeries[]
}

const props = defineProps<{ radar?: RadarData | null }>()
const el = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function render() {
  if (!chart) return
  // 数据置空时清空图表，避免残留上一次的旧数据
  if (!props.radar) {
    chart.clear()
    return
  }
  const series = props.radar.series || []
  // max=0 守卫：避免指标 max 为 0 时雷达值渲染异常（NaN/0 分母）
  const indicators = (props.radar.indicators || []).map((ind) => ({
    name: ind.name,
    max: ind.max > 0 ? ind.max : 100,
  }))
  chart.setOption({
    tooltip: {},
    legend: { data: series.map((s) => s.name) },
    radar: {
      indicator: indicators,
      radius: '62%',
    },
    series: [{
      type: 'radar',
      data: series.map((s) => ({
        name: s.name,
        value: (s.value || []).map((v) => (Number.isFinite(v) ? v : 0)),
        areaStyle: { opacity: 0.12 },
      })),
    }],
  }, true)
}

onMounted(() => {
  if (!el.value) return
  chart = echarts.init(el.value)
  render()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
})

function onResize() {
  chart?.resize()
}

watch(() => props.radar, render, { deep: true })
</script>

<style scoped>
.radar-chart { width: 100%; height: 360px; }
</style>
