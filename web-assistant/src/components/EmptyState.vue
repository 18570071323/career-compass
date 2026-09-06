<template>
  <div class="empty-state">
    <svg class="es-illus" width="120" height="120" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- ===== 文档场景：简历/岗位通用 ===== -->
      <g v-if="illustration === 'doc'">
        <rect x="30" y="18" width="58" height="78" rx="8" fill="#F0F6FF" stroke="#A8C5F5" stroke-width="3" />
        <path d="M43 36h32M43 48h32M43 60h22" stroke="#C0D5F5" stroke-width="3" stroke-linecap="round" />
        <circle cx="86" cy="82" r="16" stroke="#409EFF" stroke-width="3.5" />
        <path d="M97 93l10 10" stroke="#409EFF" stroke-width="3.5" stroke-linecap="round" />
        <path d="M38 84l4 4 8-9" stroke="#67C23A" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
      </g>
      <!-- ===== 任务清单场景：批量任务 ===== -->
      <g v-else-if="illustration === 'list'">
        <rect x="32" y="20" width="56" height="80" rx="8" fill="#F0F6FF" stroke="#A8C5F5" stroke-width="3" />
        <rect x="45" y="14" width="30" height="12" rx="4" fill="#fff" stroke="#C0D5F5" stroke-width="3" />
        <path d="M43 48h34M43 62h34M43 76h20" stroke="#C0D5F5" stroke-width="3" stroke-linecap="round" />
        <circle cx="76" cy="76" r="12" fill="#fff" stroke="#67C23A" stroke-width="3" />
        <path d="M71 76l4 4 7-8" stroke="#67C23A" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
      </g>
      <!-- ===== 人选场景：潜在人选/对比 ===== -->
      <g v-else>
        <circle cx="52" cy="42" r="14" fill="#F0F6FF" stroke="#A8C5F5" stroke-width="3" />
        <path d="M30 92c0-14 10-22 22-22s22 8 22 22" fill="#F0F6FF" stroke="#A8C5F5" stroke-width="3" stroke-linecap="round" />
        <circle cx="84" cy="56" r="22" stroke="#409EFF" stroke-width="3.5" stroke-dasharray="4 5" />
        <circle cx="84" cy="56" r="8" fill="#409EFF" opacity="0.25" />
        <path d="M102 74l8 8" stroke="#409EFF" stroke-width="3.5" stroke-linecap="round" />
      </g>
    </svg>
    <div class="es-title">{{ title }}</div>
    <div v-if="description" class="es-desc">{{ description }}</div>
    <div v-if="$slots.action" class="es-action"><slot name="action" /></div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  illustration?: 'doc' | 'list' | 'people'
  title: string
  description?: string
}>()
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 28px 0 22px;
}
.es-illus { opacity: 0.95; }
.es-title { font-size: 14px; font-weight: 600; color: #606266; margin-top: 4px; }
.es-desc { font-size: 12.5px; color: #909399; max-width: 320px; text-align: center; line-height: 1.6; }
.es-action { margin-top: 10px; }
</style>
