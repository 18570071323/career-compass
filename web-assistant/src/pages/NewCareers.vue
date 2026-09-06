<template>
  <div class="careers-page">
    <!-- 工具栏 -->
    <el-card shadow="never" class="tool-card">
      <div class="intro">
        人社部近年公示/确立的新职业速览（家庭教育指导师、老年人能力评估师、碳排放管理员……）——多为考证/培训通道，
        帮"专业不知道往哪走"的你看清新兴出口；本库为方向参考，不参与岗位匹配打分。
      </div>
      <el-alert type="info" :closable="false" class="disclaimer" :title="careerDisclaimer" />
      <div class="toolbar">
        <el-input v-model="careerQ" placeholder="搜索：方向/技能，如 养老、家庭教育" clearable style="width: 260px" @keyup.enter="applyQuery" />
        <el-input v-model="careerMajor" placeholder="填你的专业，适配方向自动排前（如 护理学）" clearable style="width: 280px" @keyup.enter="applyQuery" />
        <el-button type="primary" plain @click="applyQuery">查询</el-button>
        <el-button v-if="careerQ || careerMajor || careerGroup" link @click="resetAll">重置</el-button>
      </div>
      <div class="groups">
        <span class="groups-label">赛道：</span>
        <el-check-tag
          v-for="g in careerGroups" :key="g"
          :checked="careerGroup === g"
          @change="careerGroup = careerGroup === g ? '' : g"
        >{{ g }}</el-check-tag>
      </div>
      <div class="count-line">
        共 {{ careerAll.length }} 个方向
        <template v-if="careerMajorQuery">｜ 按「{{ careerMajorQuery }}」适配排序</template>
        <template v-if="careerList.length < careerAll.length">｜ 当前显示 {{ careerList.length }} 个</template>
      </div>
    </el-card>

    <!-- 卡片网格 -->
    <div v-loading="careersLoading" class="grid-wrap">
      <div v-if="careerList.length" class="grid">
        <div v-for="c in careerList" :key="c.name" class="card">
          <div class="card-head">
            <b class="cname">{{ c.name }}</b>
            <el-tag size="small" type="success">{{ c.group }}</el-tag>
            <el-tag v-if="careerMajorQuery && c._rel > 0" size="small" type="danger">专业适配</el-tag>
          </div>
          <div class="cofficial">{{ c.official }}</div>
          <div class="csummary">{{ c.summary }}</div>
          <div class="crow"><span class="clabel">适配专业</span>
            <el-tag v-for="m in c.fit_majors" :key="m" size="small" plain type="info" class="chip">{{ m }}</el-tag>
          </div>
          <div class="crow"><span class="clabel">建议补技能</span>
            <div class="skill-tags">
              <el-tag v-for="s in c.skills" :key="s" size="small" plain class="chip">{{ s }}</el-tag>
            </div>
          </div>
          <div class="crow cert"><span class="clabel">可考证</span><span>{{ c.cert }}</span></div>
          <div class="ctip">💡 {{ c.tip }}</div>
        </div>
      </div>
      <el-empty v-else-if="!careersLoading" description="没有匹配的新职业方向，换个关键词或赛道试试" :image-size="80" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const careerQ = ref('')
const careerMajor = ref('')
const careerQQuery = ref('')
const careerMajorQuery = ref('')
const careerGroup = ref('')
const careerGroups = ref<string[]>([])
const careerDisclaimer = ref('')
const careersLoading = ref(false)
const careerAll = ref<any[]>([])

const careerList = computed(() => {
  const ql = careerQQuery.value.toLowerCase()
  const ml = careerMajorQuery.value.toLowerCase()
  let list = careerAll.value.filter((c: any) => {
    if (careerGroup.value && c.group !== careerGroup.value) return false
    if (ql) {
      const blob = `${c.name} ${c.summary || ''} ${(c.skills || []).join(' ')} ${c.cert || ''}`.toLowerCase()
      if (!blob.includes(ql)) return false
    }
    return true
  })
  if (ml) {
    list = list
      .map((c: any) => ({
        ...c,
        _rel: (c.fit_majors || []).filter((k: string) => ml.includes(k.toLowerCase())).length,
      }))
      .sort((a: any, b: any) => b._rel - a._rel)
  }
  return list
})

async function loadCareers() {
  careersLoading.value = true
  try {
    const res = await api.candidate.newCareers()
    careerAll.value = res.items || []
    careerGroups.value = res.groups || []
    careerDisclaimer.value = res.disclaimer || ''
  } catch {
    ElMessage.warning('新职业方向加载失败，请稍后重试')
  } finally {
    careersLoading.value = false
  }
}
function applyQuery() {
  careerQQuery.value = careerQ.value.trim()
  careerMajorQuery.value = careerMajor.value.trim()
}
function resetAll() {
  careerQ.value = ''
  careerMajor.value = ''
  careerGroup.value = ''
  applyQuery()
}
loadCareers()
</script>

<style scoped>
.careers-page { display: flex; flex-direction: column; gap: 14px; }
.tool-card { border-radius: 8px; }
.intro { font-size: 13px; color: #606266; line-height: 1.8; }
.disclaimer { margin: 12px 0 14px; }
.toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.groups { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.groups-label { color: #909399; font-size: 13px; }
.count-line { margin-top: 10px; font-size: 12.5px; color: #909399; }
.grid-wrap { min-height: 200px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }
.card { border: 1px solid #e4e7ed; border-radius: 10px; padding: 14px 16px; background: #fff; display: flex; flex-direction: column; gap: 8px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03); }
.card-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cname { font-size: 16px; color: #1f2d3d; }
.cofficial { font-size: 12px; color: #b7791f; background: #fdf6ec; border-radius: 4px; padding: 2px 8px; align-self: flex-start; }
.csummary { font-size: 13px; color: #606266; line-height: 1.75; }
.crow { font-size: 12.5px; color: #303133; line-height: 1.6; display: flex; gap: 8px; align-items: flex-start; }
.clabel { color: #909399; flex: none; font-weight: 500; padding-top: 2px; }
.cert { display: block; }
.skill-tags { flex: 1; }
.chip { margin: 1px 3px 1px 0; }
.ctip { font-size: 12px; color: #8a6d3b; background: #faf3e3; border-radius: 6px; padding: 7px 10px; line-height: 1.65; }
</style>
