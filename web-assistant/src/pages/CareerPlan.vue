<template>
  <div class="plan-page">
    <el-card shadow="never" class="step-card">
      <template #header>
        <div class="card-title">
          <el-icon><Compass /></el-icon> 求职导航 · 先告诉我想做什么，只问你相关的题
        </div>
      </template>

      <!-- ============ 目标（想做的事 = 目标，放第一位） ============ -->
      <div class="sec-title">🎯 你想做什么？（目标放第一位）</div>
      <el-form label-width="110px" class="qform">
        <el-form-item label="目标类型">
          <el-radio-group v-model="f.target_kind">
            <el-radio-button value="job">直接就业</el-radio-button>
            <el-radio-button value="grad">考研</el-radio-button>
            <el-radio-button value="civil">考公/考编</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 就业 -->
        <template v-if="f.target_kind === 'job'">
          <el-form-item label="目标岗位方向">
            <el-select v-model="f.target" filterable style="width: 320px" placeholder="从岗位库已有方向选择" @change="onTargetChange">
              <el-option v-for="d in directionOptions" :key="d.name" :label="d.name" :value="d.name" />
            </el-select>
            <span v-if="targetMeta.found" class="target-info">
              {{ targetMeta.name }}方向 · 岗位库 {{ targetMeta.jd_count }} 条样本
            </span>
            <div class="hint">没有明确方向也正常：可在下方"经历盘点/技能"填写后，直接选一个目标以终为始去补</div>
          </el-form-item>
          <el-form-item v-if="targetSkillOptions.length" label="我会的技能">
            <div class="skill-chips">
              <el-check-tag
                v-for="s in targetSkillOptions"
                :key="s"
                :checked="f.skills_selected.includes(s)"
                @change="toggleSkill(s)"
              >{{ s }}</el-check-tag>
            </div>
            <div class="hint">勾选你已具备/在学的核心技能——缺的会进入"差距清单"</div>
          </el-form-item>
        </template>

        <!-- 考研 -->
        <template v-if="f.target_kind === 'grad'">
          <el-form-item label="本专业/跨考">
            <el-radio-group v-model="f.grad_scope">
              <el-radio-button value="same">本专业考研</el-radio-button>
              <el-radio-button value="cross">跨专业考研</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="预计考试时间">
            <el-select v-model="f.grad_exam" style="width: 380px">
              <el-option v-for="o in gradExamOptions" :key="o.v" :label="o.label" :value="o.v" />
            </el-select>
          </el-form-item>
          <el-form-item label="专业排名">
            <el-select v-model="f.grad_rank" style="width: 300px">
              <el-option v-for="o in gradRankOptions" :key="o.v" :label="o.label" :value="o.v" />
            </el-select>
            <div class="hint">保研主要看专业排名 + 本校推免资格；不知道就先查：找辅导员问清名次与前 X% 线</div>
          </el-form-item>
          <div class="hint note-line">开始准备的时间因人而异——按你选的考试时间和每周投入给"最晚启动建议"，不套标准模板。</div>
        </template>

        <!-- 考公/考编 -->
        <template v-if="f.target_kind === 'civil'">
          <el-form-item label="考试类型">
            <el-radio-group v-model="f.civil_type">
              <el-radio-button v-for="o in civilTypeOptions" :key="o.v" :value="o.v">{{ o.label }}</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="报考窗口">
            <el-select v-model="f.civil_exam" style="width: 360px">
              <el-option v-for="o in civilExamOptions" :key="o.v" :label="o.label" :value="o.v" />
            </el-select>
          </el-form-item>
          <el-form-item label="政治面貌">
            <el-radio-group v-model="f.party">
              <el-radio-button value="none">群众/其他</el-radio-button>
              <el-radio-button value="activist">入党积极分子</el-radio-button>
              <el-radio-button value="prep">预备党员</el-radio-button>
              <el-radio-button value="member">正式党员</el-radio-button>
            </el-radio-group>
            <div class="hint">考公建议先入党：选调生/定向选调基本要求党员，普通岗位也有党员限制；入党流程一般 1 年以上</div>
          </el-form-item>
        </template>
      </el-form>

      <!-- ============ 基本信息 ============ -->
      <div class="sec-title">基本与你相关的信息</div>
      <el-form label-width="110px" class="qform">
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="当前年级">
              <el-select v-model="f.grade" style="width: 100%">
                <el-option v-for="g in ['大一', '大二', '大三', '大四', '研一', '研二']" :key="g" :label="g" :value="g" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="学校层次">
              <el-select v-model="f.school_tier" style="width: 100%">
                <el-option v-for="s in ['985', '211', '普通一本', '二本', '专科', '海外院校']" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="专业">
              <el-input v-model="f.major" placeholder="如：人力资源管理" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="8" v-if="f.target_kind === 'job'">
            <el-form-item label="GPA/排名">
              <el-input v-model="f.gpa" placeholder="如 3.4/4.0 或 前 30%（选填）" />
            </el-form-item>
          </el-col>
          <el-col :span="f.target_kind === 'job' ? 8 : 12">
            <el-form-item label="距离毕业">
              <el-select v-model="f.semesters_left" style="width: 100%">
                <el-option v-for="n in [0, 1, 2, 3, 4, 5, 6]" :key="n" :label="n === 0 ? '已到毕业季' : `约 ${n} 个学期`" :value="n" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="f.target_kind === 'job' ? 8 : 12">
            <el-form-item label="每周可投入">
              <el-select v-model="f.weekly_hours" style="width: 100%">
                <el-option v-for="h in [2, 5, 10, 15, 20, 30]" :key="h" :label="`${h} 小时`" :value="h" />
              </el-select>
              <div v-if="f.target_kind !== 'job'" class="hint">用于估算"最晚启动点"</div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item v-if="f.target_kind === 'civil'" label="学生干部">
          <el-input v-model="f.org_role" style="width: 360px" placeholder="如：班长/团支书（选调/定向岗很加分）" />
        </el-form-item>
      </el-form>

      <!-- ============ 经历盘点（按目标出题） ============ -->
      <template v-if="f.target_kind === 'job'">
        <div class="sec-title">📦 经历盘点（如实勾选即可，空白没关系）</div>
        <el-form label-width="110px" class="qform">
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="实习经历">
                <el-select v-model="f.intern_count" style="width: 100%">
                  <el-option v-for="n in [0, 1, 2, 3]" :key="n" :label="n === 0 ? '还没有实习' : `${n} 段`" :value="n" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="16">
              <el-form-item v-if="f.intern_count > 0" label="实习方向">
                <el-select v-model="f.intern_fields" multiple filterable allow-create default-first-option style="width: 100%" placeholder="如：人力、运营、行政（回车添加）" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="项目/课程设计">
                <el-select v-model="f.project_count" style="width: 100%">
                  <el-option v-for="n in [0, 1, 2, 3]" :key="n" :label="n === 0 ? '无' : `${n} 个`" :value="n" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="竞赛获奖">
                <el-select v-model="f.contest_count" style="width: 100%">
                  <el-option v-for="n in [0, 1, 2, 3]" :key="n" :label="n === 0 ? '无' : `${n} 项`" :value="n" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="学生组织角色">
                <el-input v-model="f.org_role" placeholder="如：班长/部长/团支书（选填）" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row v-if="f.project_count > 0 || f.contest_count > 0" :gutter="20">
            <el-col :span="12" v-if="f.project_count > 0">
              <el-form-item label="项目/课设内容">
                <el-input v-model="f.project_detail" type="textarea" :rows="2" placeholder="做了什么（选填），如：校园二手小程序｜Python+MySQL｜独立写后端｜上线约500人用" />
              </el-form-item>
            </el-col>
            <el-col :span="12" v-if="f.contest_count > 0">
              <el-form-item label="竞赛获奖内容">
                <el-input v-model="f.contest_detail" type="textarea" :rows="2" placeholder="获奖情况（选填），如：蓝桥杯省二｜个人参赛，负责算法与文档" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="已有证书">
            <el-select v-model="f.certs" multiple filterable allow-create default-first-option style="width: 100%" placeholder="如：普通话二甲、英语四级（回车添加）" />
          </el-form-item>
        </el-form>

        <div class="sec-title">💡 特质与偏好（凭感觉选，无对错）</div>
        <el-form label-width="110px" class="qform">
          <el-form-item label="你更像哪种">
            <el-radio-group v-model="f.trait">
              <el-radio-button value="people">爱与人打交道</el-radio-button>
              <el-radio-button value="data">爱数据逻辑</el-radio-button>
              <el-radio-button value="creative">爱创意表达</el-radio-button>
              <el-radio-button value="exec">爱细致执行</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="择业倾向">
            <el-radio-group v-model="f.stable_pref">
              <el-radio :value="true">求稳优先（国企/银行/编制向）</el-radio>
              <el-radio :value="false">成长优先（大厂/新兴行业）</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
      </template>

      <template v-else-if="f.target_kind === 'grad'">
        <div class="sec-title">🔬 科研与竞赛（复试素材，没有也没关系）</div>
        <el-form label-width="110px" class="qform">
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="项目/科研">
                <el-select v-model="f.project_count" style="width: 100%">
                  <el-option v-for="n in [0, 1, 2, 3]" :key="n" :label="n === 0 ? '无' : `${n} 个`" :value="n" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="竞赛获奖">
                <el-select v-model="f.contest_count" style="width: 100%">
                  <el-option v-for="n in [0, 1, 2, 3]" :key="n" :label="n === 0 ? '无' : `${n} 项`" :value="n" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="英语等级">
                <el-select v-model="f.certs" multiple filterable allow-create default-first-option style="width: 100%" placeholder="如：英语四级、六级（回车添加）" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row v-if="f.project_count > 0 || f.contest_count > 0" :gutter="20">
            <el-col :span="12" v-if="f.project_count > 0">
              <el-form-item label="科研/项目内容">
                <el-input v-model="f.project_detail" type="textarea" :rows="2" placeholder="做了什么（选填），如：大创项目｜负责数据处理与论文初稿" />
              </el-form-item>
            </el-col>
            <el-col :span="12" v-if="f.contest_count > 0">
              <el-form-item label="竞赛获奖内容">
                <el-input v-model="f.contest_detail" type="textarea" :rows="2" placeholder="获奖情况（选填），如：数学建模省一｜负责建模与论文" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </template>

      <!-- ============ 你的擅长（基础能力 vs 可职业化特长） ============ -->
      <div class="sec-title">✨ 你的擅长</div>
      <el-form label-width="110px" class="qform">
        <template v-if="f.target_kind === 'job'">
          <el-form-item label="基础能力">
            <div class="skill-chips">
              <el-check-tag
                v-for="b in basicChips"
                :key="b"
                :checked="f.basic_skills.includes(b)"
                @change="toggleIn('basic_skills', b)"
              >{{ b }}</el-check-tag>
            </div>
            <div class="hint">基础能力谁都要有，只做支撑、不算职业方向</div>
          </el-form-item>
        </template>
        <el-form-item :label="f.target_kind === 'job' ? '可当职业的特长' : '可当职业的特长'">
          <div class="skill-chips">
            <el-check-tag
              v-for="s in specialChips"
              :key="s.key"
              :checked="f.special_skills.includes(s.key)"
              @change="toggleIn('special_skills', s.key)"
            >{{ s.label }}</el-check-tag>
          </div>
          <div class="hint">{{ f.target_kind === 'job' ? '勾了可直接推荐到对应方向' : '选填：如写作对申论、表达对面试是加分项' }}</div>
        </el-form-item>
        <el-form-item label="作品/成果">
          <el-input v-model="f.special_note" style="width: 100%" placeholder="特长作品/成果（选填），如：运营账号1万粉、剪过10条商单、摄影获过奖" />
        </el-form-item>
      </el-form>

      <div class="submit-row">
        <el-button type="primary" size="large" :loading="planning" @click="doPlan">生成我的路线图</el-button>
        <span v-if="f.target_kind === 'job' && f.target" class="target-hint">目标：{{ f.target }}</span>
        <span v-else-if="f.target_kind !== 'job'" class="target-hint">目标：{{ kindSummary }}</span>
      </div>
    </el-card>

    <!-- ============ 结果区 ============ -->
    <div v-if="result" v-loading="planning">
      <el-card shadow="never" class="step-card">
        <template #header>
          <div class="card-title"><el-icon><DataAnalysis /></el-icon> 你的规划 · 目标「{{ result.target }}」</div>
        </template>

        <div class="overall-box" v-if="result.overall">
          <div class="overall-label">{{ result.overall_source === 'llm' ? '🤖 AI 总体判断' : '总体判断' }}</div>
          <p class="overall-text">{{ result.overall }}</p>
        </div>

        <div v-if="result.profile?.length" class="sec-title">🧾 画像定位</div>
        <el-descriptions v-if="result.profile?.length" :column="1" border size="small" class="mb8">
          <el-descriptions-item v-for="(row, i) in result.profile" :key="i" :label="row.k">
            {{ row.v }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="sec-title">📋 差距清单</div>
        <el-table :data="result.gaps" size="small" border>
          <el-table-column prop="dim" label="维度" width="130" />
          <el-table-column prop="item" label="差距" min-width="200" />
          <el-table-column prop="note" label="说明" min-width="280" />
          <el-table-column label="优先级" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.priority === 'high' ? 'danger' : row.priority === 'mid' ? 'warning' : 'success'" size="small">
                {{ row.priority === 'high' ? '高' : row.priority === 'mid' ? '中' : '低' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <div class="sec-title">🗺️ 行动路线图</div>
        <div v-for="(ph, i) in result.roadmap" :key="i" class="phase">
          <div class="phase-title"><b>{{ ph.phase }}</b></div>
          <ul class="phase-actions">
            <li v-for="(a, j) in ph.actions" :key="j" class="pa-item">
              <el-tag size="small" :type="kindType(a.kind)" class="pa-kind">{{ kindLabel(a.kind) }}</el-tag>
              <b>{{ a.title }}</b>
              <el-tag v-if="a.priority === 'high'" size="small" type="danger" class="pa-pri">优先</el-tag>
              <div class="pa-detail">{{ a.detail }}</div>
            </li>
          </ul>
        </div>

        <template v-if="result.contests?.length">
          <div class="sec-title">🏆 推荐比赛（含金量已排序）</div>
          <el-table :data="result.contests" size="small" border>
            <el-table-column prop="name" label="比赛" min-width="220" />
            <el-table-column prop="host" label="主办" min-width="140" />
            <el-table-column label="含金量" width="90" align="center">
              <template #default="{ row }"><span class="star">{{ '★'.repeat(row.value) }}<span class="dim">{{ '★'.repeat(5 - row.value) }}</span></span></template>
            </el-table-column>
            <el-table-column label="难度" width="70" align="center">
              <template #default="{ row }"><el-tag :type="row.difficulty >= 4 ? 'danger' : row.difficulty >= 3 ? 'warning' : 'success'" size="small">{{ row.difficulty }}/5</el-tag></template>
            </el-table-column>
            <el-table-column prop="when" label="时机" min-width="120" />
            <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip />
          </el-table>
        </template>

        <template v-if="result.cert_advice?.length">
          <div class="sec-title">📜 建议证书</div>
          <div class="cert-row" v-for="(c, i) in result.cert_advice" :key="i">
            <el-tag type="warning" size="small" class="pa-kind">证书</el-tag> <b>{{ c.name }}</b> — {{ c.note }}
          </div>
        </template>

        <el-alert type="info" :closable="false" class="mb8 disc" :title="result.disclaimer" />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Compass, DataAnalysis } from '@element-plus/icons-vue'
import { api } from '../api/client'

const gradExamOptions = [
  { v: '12m', label: '应届考研：明年 12 月左右（约一年后）' },
  { v: '24m', label: '后年 12 月左右（约两年后）' },
  { v: '36m', label: '更久以后' },
  { v: 'unknown', label: '还没定（先给通用框架）' },
]
const gradRankOptions = [
  { v: 'top5', label: '前 5% 以内（保研希望很大）' },
  { v: 'top10', label: '前 10% 左右（有机会冲保研）' },
  { v: 'top20', label: '前 20% 左右（可争取）' },
  { v: 'mid', label: '中游（50% 上下）' },
  { v: 'low', label: '靠后' },
  { v: 'unknown', label: '不清楚/没算过' },
]
const civilTypeOptions = [
  { v: 'national', label: '国考' },
  { v: 'province', label: '省考' },
  { v: 'career_unit', label: '事业编' },
]
const civilExamOptions = [
  { v: 'gradyear', label: '应届报考（毕业那年的公考季）' },
  { v: 'after', label: '毕业后再备考一年' },
  { v: 'unknown', label: '还没定' },
]

// 擅长：基础能力（不算职业方向，只作支撑） vs 可职业化特长（→ 岗位库方向）
const BASIC_CHIPS = ['PPT/汇报', 'Excel/表格', '沟通表达', '英语读写', '组织协调', '其他基础能力']
const SPECIAL_CHIPS = [
  { key: 'media', label: '摄影/剪辑' },
  { key: 'writing', label: '写作/文案' },
  { key: 'design', label: '设计/绘画' },
  { key: 'video', label: '视频/直播' },
  { key: 'host', label: '主持/演讲' },
  { key: 'code', label: '编程/开发' },
  { key: 'data', label: '数据分析' },
]

const f = reactive({
  target_kind: 'job',
  target: '',
  grad_scope: 'same',
  grad_exam: '12m',
  grad_rank: 'unknown',
  civil_type: 'national',
  civil_exam: 'gradyear',
  party: 'none',
  grade: '大三',
  school_tier: '普通一本',
  major: '',
  gpa: '',
  semesters_left: 3,
  weekly_hours: 10,
  intern_count: 0,
  intern_fields: [] as string[],
  project_count: 0,
  project_detail: '',
  contest_count: 0,
  contest_detail: '',
  org_role: '',
  certs: [] as string[],
  trait: 'people',
  stable_pref: true,
  basic_skills: [] as string[],
  special_skills: [] as string[],
  special_note: '',
  skills_selected: [] as string[],
})

const directionOptions = ref<any[]>([])
const targetMeta = ref<any>({ found: false, core_skills: [], toolchain: [], jd_count: 0 })
const targetSkillOptions = computed(() => [...new Set([...(targetMeta.value.toolchain || []), ...(targetMeta.value.core_skills || [])])])
const basicChips = BASIC_CHIPS
const specialChips = SPECIAL_CHIPS
const planning = ref(false)
const result = ref<any>(null)

function toggleIn(field: 'basic_skills' | 'special_skills', key: string) {
  const i = f[field].indexOf(key)
  if (i >= 0) f[field].splice(i, 1)
  else f[field].push(key)
}

const kindSummary = computed(() => {
  if (f.target_kind === 'job') return f.target || '直接就业'
  if (f.target_kind === 'grad') return '考研'
  return '考公/考编'
})

async function loadTargets() {
  try {
    const res = await api.candidate.categories()
    const flat: any[] = []
    ;(res.functions || []).forEach((fn: any) => (fn.children || []).forEach((c: any) => flat.push({ name: c.name })))
    directionOptions.value = flat
  } catch {
    ElMessage.warning('目标方向加载失败，请刷新重试')
  }
}

async function onTargetChange(name: string) {
  f.skills_selected = []
  targetMeta.value = { found: false, core_skills: [], toolchain: [], jd_count: 0 }
  if (!name) return
  try {
    const res = await api.candidate.directionProfile(name)
    targetMeta.value = res
  } catch {
    targetMeta.value = { found: false, core_skills: [], toolchain: [], jd_count: 0 }
  }
}

function toggleSkill(s: string) {
  const i = f.skills_selected.indexOf(s)
  if (i >= 0) f.skills_selected.splice(i, 1)
  else f.skills_selected.push(s)
}

async function doPlan() {
  if (f.target_kind === 'job' && !f.target) {
    ElMessage.warning('请先选择直接就业的目标岗位方向')
    return
  }
  planning.value = true
  result.value = null
  try {
    const res = await api.candidate.careerPlan(JSON.parse(JSON.stringify(f)))
    if (res.error) {
      ElMessage.warning(res.error)
    } else {
      result.value = res
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  } catch (e: any) {
    ElMessage.error(e.message || '生成失败，请稍后重试')
  } finally {
    planning.value = false
  }
}

const KIND_LABEL: Record<string, string> = {
  skill: '技能', cert: '证书', contest: '比赛', intern: '实习', exp: '经历',
  check: '冲刺', note: '提醒', info: '信息', plan: '计划', study: '学习', exam: '备考', interview: '复试/面试',
}
const KIND_TYPE: Record<string, string> = {
  skill: 'primary', cert: 'warning', contest: 'success', intern: 'danger', exp: 'info',
  check: 'danger', note: 'info', info: 'primary', plan: 'warning', study: 'primary', exam: 'danger', interview: 'warning',
}
function kindLabel(k: string) { return KIND_LABEL[k] || k }
function kindType(k: string) { return (KIND_TYPE as any)[k] || 'info' }
</script>

<style scoped>
.plan-page { display: flex; flex-direction: column; gap: 16px; }
.step-card { border-radius: 8px; }
.card-title { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.sec-title { font-size: 14px; font-weight: 700; color: #1f2d3d; margin: 6px 0 12px; padding: 8px 0 2px; border-bottom: 1px dashed #e4e7ed; }
.qform { margin-bottom: 6px; }
.hint { font-size: 12px; color: #c0c4cc; margin-top: 6px; width: 100%; }
.note-line { margin-top: 2px; }
.target-info { margin-left: 12px; font-size: 12.5px; color: #909399; }
.skill-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.submit-row { margin-top: 16px; display: flex; align-items: center; gap: 12px; }
.target-hint { color: #909399; font-size: 13px; }
.mb8 { margin-bottom: 10px; }
.disc { margin-top: 16px; }
.overall-box { background: linear-gradient(135deg, #eff6ff, #f5f3ff); border: 1px solid #e0e7ff; border-radius: 10px; padding: 12px 16px; margin-bottom: 12px; }
.overall-label { font-size: 13px; font-weight: 700; color: #4f46e5; }
.overall-text { margin: 6px 0 0; font-size: 13.5px; line-height: 1.8; color: #1f2d3d; }
.phase { border: 1px solid #e4e7ed; border-radius: 8px; padding: 10px 14px; margin-bottom: 10px; background: #fafbfd; }
.phase-title { margin-bottom: 8px; font-size: 13.5px; color: #1f2d3d; }
.phase-actions { margin: 0; padding-left: 0; list-style: none; }
.pa-item { padding: 6px 0; border-top: 1px dashed #eceff3; font-size: 13px; }
.pa-item:first-child { border-top: none; }
.pa-kind { margin-right: 6px; }
.pa-pri { margin-left: 6px; }
.pa-detail { color: #606266; font-size: 12.5px; line-height: 1.7; margin: 4px 0 0 2px; }
.star { color: #f59e0b; letter-spacing: 1px; }
.star .dim { color: #e5e7eb; }
.cert-row { font-size: 13px; margin-bottom: 8px; color: #303133; }
</style>
