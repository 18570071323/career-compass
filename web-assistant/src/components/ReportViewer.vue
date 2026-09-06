<template>
  <div class="report">
    <div v-if="html" class="report-body" v-html="html"></div>
    <el-empty v-else description="暂无报告" :image-size="60" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps<{ markdown?: string | null }>()

const html = computed(() => {
  if (!props.markdown) return ''
  // 按次传参配置，避免模块级全局 setOptions 副作用
  const raw = marked.parse(props.markdown, { gfm: true, breaks: true }) as string
  return DOMPurify.sanitize(raw)
})
</script>

<style scoped>
.report-body {
  font-size: 14px;
  line-height: 1.8;
  color: #303133;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 20px 24px;
  max-height: 640px;
  overflow: auto;
}
.report-body :deep(h1) {
  font-size: 22px;
  font-weight: 700;
  border-bottom: 2px solid #409eff;
  padding-bottom: 10px;
  margin: 0 0 18px;
  color: #1f2d3d;
}
.report-body :deep(h2) {
  font-size: 17px;
  font-weight: 600;
  margin: 22px 0 10px;
  color: #1f2d3d;
  padding-left: 10px;
  border-left: 4px solid #409eff;
}
.report-body :deep(h3) {
  font-size: 15px;
  font-weight: 600;
  margin: 16px 0 8px;
  color: #1f2d3d;
}
.report-body :deep(p) {
  margin: 8px 0;
}
.report-body :deep(strong) {
  font-weight: 700;
  color: #1f2d3d;
}
.report-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 13px;
}
.report-body :deep(th) {
  background: #f0f6ff;
  color: #409eff;
  font-weight: 600;
  text-align: left;
  padding: 8px 12px;
  border: 1px solid #dbe7f7;
}
.report-body :deep(td) {
  padding: 8px 12px;
  border: 1px solid #e4e7ed;
}
.report-body :deep(tr:nth-child(even) td) {
  background: #fafbfd;
}
.report-body :deep(ul),
.report-body :deep(ol) {
  padding-left: 22px;
  margin: 8px 0;
}
.report-body :deep(li) {
  margin: 4px 0;
}
.report-body :deep(blockquote) {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  margin: 10px 0;
  padding: 8px 14px;
  color: #8a6d3b;
  border-radius: 0 6px 6px 0;
}
.report-body :deep(code) {
  background: #f5f7fa;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 13px;
  color: #c0392b;
}
.report-body :deep(pre) {
  background: #2b3a4a;
  color: #d6e2ee;
  padding: 12px 16px;
  border-radius: 6px;
  overflow: auto;
  font-size: 13px;
}
.report-body :deep(pre code) {
  background: transparent;
  color: inherit;
}
.report-body :deep(hr) {
  border: none;
  border-top: 1px solid #ebeef5;
  margin: 16px 0;
}
</style>
