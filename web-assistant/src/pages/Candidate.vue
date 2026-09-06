<template>
  <div class="candidate-page">
    <el-tabs v-model="mode" class="mode-tabs">
      <el-tab-pane label="求职导航" name="plan" />
      <el-tab-pane label="社招求职（有明确 JD）" name="social" />
      <el-tab-pane label="校招求职（无明确 JD）" name="campus" />
      <el-tab-pane label="新职业方向" name="careers" />
      <el-tab-pane label="公司避雷清单" name="companies" />
    </el-tabs>
    <Transition name="fade" mode="out-in">
      <CareerPlan v-if="mode === 'plan'" :key="'plan'" />
      <CandidateSocial v-else-if="mode === 'social'" :key="'social'" />
      <CandidateCampus v-else-if="mode === 'campus'" :key="'campus'" />
      <NewCareers v-else-if="mode === 'careers'" :key="'careers'" />
      <CompanyWatch v-else :key="'companies'" />
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import CandidateCampus from './CandidateCampus.vue'
import CandidateSocial from './CandidateSocial.vue'
import CareerPlan from './CareerPlan.vue'
import CompanyWatch from './CompanyWatch.vue'
import NewCareers from './NewCareers.vue'

const mode = ref('plan')
</script>

<style scoped>
.candidate-page { display: flex; flex-direction: column; gap: 16px; }
.mode-tabs :deep(.el-tabs__content) { display: none; }
</style>
