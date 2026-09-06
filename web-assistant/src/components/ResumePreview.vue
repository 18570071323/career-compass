<template>
  <div class="preview-wrap">
    <Transition name="fade" mode="out-in">
    <div :key="style" class="preview-stage">
    <!-- ========== 简约现代 Modern ========== -->
    <div v-if="style === 'modern'" class="resume-sheet sheet-modern">
      <header class="m-header">
        <div class="m-avatar">{{ initial }}</div>
        <div class="m-head-main">
          <h1 class="m-name">{{ personal.name || '姓名' }}</h1>
          <div class="m-position">{{ personal.position || '' }}</div>
          <div class="m-contact">
            <span v-if="personal.phone">{{ personal.phone }}</span>
            <span v-if="personal.email">{{ personal.email }}</span>
            <span v-if="personal.city">{{ personal.city }}</span>
            <span v-if="personal.github">{{ personal.github }}</span>
            <span v-if="personal.blog">{{ personal.blog }}</span>
          </div>
        </div>
      </header>
      <section v-if="content.summary">
        <h2 class="m-sec">个人简介</h2>
        <p class="m-text">{{ content.summary }}</p>
      </section>
      <section v-if="content.education.length">
        <h2 class="m-sec">教育背景</h2>
        <div v-for="e in content.education" :key="e.school + e.period" class="m-item">
          <div class="m-item-head"><b>{{ e.school }}</b><span class="m-item-right">{{ e.period }}</span></div>
          <div class="m-item-sub">{{ e.degree }} · {{ e.major }}<template v-if="e.gpa"> · {{ e.gpa }}</template></div>
          <div v-if="e.honors" class="m-text">{{ e.honors }}</div>
        </div>
      </section>
      <section v-if="content.internships.length">
        <h2 class="m-sec">实习经历</h2>
        <div v-for="it in content.internships" :key="it.company + it.period" class="m-item">
          <div class="m-item-head"><b>{{ it.company }}</b><span class="m-item-right">{{ it.period }}</span></div>
          <div class="m-item-sub">{{ it.position }}</div>
          <ul class="m-list"><li v-for="(p, i) in it.points" :key="i">{{ p }}</li></ul>
        </div>
      </section>
      <section v-if="content.projects.length">
        <h2 class="m-sec">项目经历</h2>
        <div v-for="p in content.projects" :key="p.name" class="m-item">
          <div class="m-item-head"><b>{{ p.name }}</b><span class="m-item-right">{{ p.period }}</span></div>
          <div class="m-item-sub">{{ p.role }}<template v-if="p.tech.length"> · 技术：{{ p.tech.join(' / ') }}</template></div>
          <ul class="m-list"><li v-for="(pt, i) in p.points" :key="i">{{ pt }}</li></ul>
        </div>
      </section>
      <section v-if="content.skills.length">
        <h2 class="m-sec">技能与证书</h2>
        <div v-for="s in content.skills" :key="s.group" class="m-item">
          <div class="m-item-sub"><b>{{ s.group }}：</b>{{ s.items.join('、') }}</div>
        </div>
        <div v-if="content.certs.length" class="m-item m-item-sub">证书：{{ content.certs.join('、') }}</div>
      </section>
      <section v-if="content.achievements.length">
        <h2 class="m-sec">荣誉与成果</h2>
        <ul class="m-list"><li v-for="(a, i) in content.achievements" :key="i">{{ a }}</li></ul>
      </section>
    </div>

    <!-- ========== 经典专业 Classic ========== -->
    <div v-else-if="style === 'classic'" class="resume-sheet sheet-classic">
      <header class="c-header">
        <h1 class="c-name">{{ personal.name || '姓名' }}</h1>
        <div class="c-position">{{ personal.position || '' }}</div>
        <div class="c-contact">
          <span v-if="personal.phone">{{ personal.phone }}</span>
          <span v-if="personal.email">{{ personal.email }}</span>
          <span v-if="personal.city">{{ personal.city }}</span>
          <span v-if="personal.github">{{ personal.github }}</span>
        </div>
      </header>
      <section v-if="content.summary">
        <h2 class="c-sec">个人简介</h2>
        <p class="c-text">{{ content.summary }}</p>
      </section>
      <section v-if="content.education.length">
        <h2 class="c-sec">教育背景</h2>
        <div v-for="e in content.education" :key="e.school" class="c-item">
          <div class="c-row"><b>{{ e.school }}</b><span class="c-right">{{ e.period }}</span></div>
          <div class="c-sub">{{ e.degree }} · {{ e.major }}<template v-if="e.gpa"> · {{ e.gpa }}</template></div>
          <div v-if="e.honors" class="c-text">{{ e.honors }}</div>
        </div>
      </section>
      <section v-if="content.internships.length">
        <h2 class="c-sec">实习经历</h2>
        <div v-for="it in content.internships" :key="it.company" class="c-item">
          <div class="c-row"><b>{{ it.company }} · {{ it.position }}</b><span class="c-right">{{ it.period }}</span></div>
          <ul class="c-list"><li v-for="(p, i) in it.points" :key="i">{{ p }}</li></ul>
        </div>
      </section>
      <section v-if="content.projects.length">
        <h2 class="c-sec">项目经历</h2>
        <div v-for="p in content.projects" :key="p.name" class="c-item">
          <div class="c-row"><b>{{ p.name }}</b><span class="c-right">{{ p.period }}</span></div>
          <div class="c-sub">{{ p.role }}<template v-if="p.tech.length"> · {{ p.tech.join(' / ') }}</template></div>
          <ul class="c-list"><li v-for="(pt, i) in p.points" :key="i">{{ pt }}</li></ul>
        </div>
      </section>
      <section v-if="content.skills.length || content.certs.length">
        <h2 class="c-sec">专业技能</h2>
        <div v-for="s in content.skills" :key="s.group" class="c-text"><b>{{ s.group }}：</b>{{ s.items.join('、') }}</div>
        <div v-if="content.certs.length" class="c-text"><b>证书：</b>{{ content.certs.join('、') }}</div>
      </section>
      <section v-if="content.achievements.length">
        <h2 class="c-sec">荣誉与成果</h2>
        <ul class="c-list"><li v-for="(a, i) in content.achievements" :key="i">{{ a }}</li></ul>
      </section>
    </div>

    <!-- ========== 创意活力 Creative ========== -->
    <div v-else-if="style === 'creative'" class="resume-sheet sheet-creative">
      <aside class="cr-side">
        <div class="cr-avatar">{{ initial }}</div>
        <h1 class="cr-name">{{ personal.name || '姓名' }}</h1>
        <div class="cr-pos">{{ personal.position || '' }}</div>
        <div class="cr-block" v-if="personal.phone || personal.email || personal.city || personal.github || personal.blog">
          <h3 class="cr-block-title">联系</h3>
          <div v-if="personal.phone">📞 {{ personal.phone }}</div>
          <div v-if="personal.email">✉️ {{ personal.email }}</div>
          <div v-if="personal.city">📍 {{ personal.city }}</div>
          <div v-if="personal.github">💻 {{ personal.github }}</div>
          <div v-if="personal.blog">🌐 {{ personal.blog }}</div>
        </div>
        <div class="cr-block" v-if="content.skills.length">
          <h3 class="cr-block-title">技能</h3>
          <div v-for="s in content.skills" :key="s.group" class="cr-skill">
            <div class="cr-skill-name">{{ s.group }}</div>
            <div class="cr-skill-items">{{ s.items.join(' · ') }}</div>
          </div>
        </div>
        <div class="cr-block" v-if="content.certs.length">
          <h3 class="cr-block-title">证书</h3>
          <div v-for="(c, i) in content.certs" :key="i">🏅 {{ c }}</div>
        </div>
      </aside>
      <main class="cr-main">
        <section v-if="content.summary">
          <h2 class="cr-sec">关于我</h2>
          <p class="cr-text">{{ content.summary }}</p>
        </section>
        <section v-if="content.education.length">
          <h2 class="cr-sec">教育背景</h2>
          <div v-for="e in content.education" :key="e.school" class="cr-item">
            <div class="cr-row"><b>{{ e.school }}</b><span class="cr-right">{{ e.period }}</span></div>
            <div class="cr-sub">{{ e.degree }} · {{ e.major }}<template v-if="e.gpa"> · {{ e.gpa }}</template></div>
          </div>
        </section>
        <section v-if="content.internships.length">
          <h2 class="cr-sec">实习经历</h2>
          <div v-for="it in content.internships" :key="it.company" class="cr-item">
            <div class="cr-row"><b>{{ it.company }} · {{ it.position }}</b><span class="cr-right">{{ it.period }}</span></div>
            <ul class="cr-list"><li v-for="(p, i) in it.points" :key="i">{{ p }}</li></ul>
          </div>
        </section>
        <section v-if="content.projects.length">
          <h2 class="cr-sec">项目经历</h2>
          <div v-for="p in content.projects" :key="p.name" class="cr-item">
            <div class="cr-row"><b>{{ p.name }}</b><span class="cr-right">{{ p.period }}</span></div>
            <div class="cr-sub">{{ p.role }}<template v-if="p.tech.length"> · {{ p.tech.join(' / ') }}</template></div>
            <ul class="cr-list"><li v-for="(pt, i) in p.points" :key="i">{{ pt }}</li></ul>
          </div>
        </section>
        <section v-if="content.achievements.length">
          <h2 class="cr-sec">荣誉与成果</h2>
          <ul class="cr-list"><li v-for="(a, i) in content.achievements" :key="i">⭐ {{ a }}</li></ul>
        </section>
      </main>
    </div>

    <!-- ========== 极客技术 Tech ========== -->
    <div v-else class="resume-sheet sheet-tech">
      <header class="t-bar">
        <div>
          <h1 class="t-name">{{ personal.name || '姓名' }}</h1>
          <div class="t-pos">{{ personal.position || '' }}</div>
        </div>
        <div class="t-contact">
          <div v-if="personal.phone">{{ personal.phone }}</div>
          <div v-if="personal.email">{{ personal.email }}</div>
          <div v-if="personal.city">{{ personal.city }}</div>
          <div v-if="personal.github">{{ personal.github }}</div>
        </div>
      </header>
      <section v-if="content.summary" class="t-sec">
        <h2 class="t-title">> 简介</h2>
        <p class="t-text">{{ content.summary }}</p>
      </section>
      <section v-if="content.education.length" class="t-sec">
        <h2 class="t-title">> 教育</h2>
        <div v-for="e in content.education" :key="e.school" class="t-row"><b>{{ e.school }}</b><span>{{ e.degree }} · {{ e.major }}<template v-if="e.gpa"> · {{ e.gpa }}</template></span><span class="t-right">{{ e.period }}</span></div>
      </section>
      <section v-if="content.internships.length" class="t-sec">
        <h2 class="t-title">> 实习</h2>
        <div v-for="it in content.internships" :key="it.company" class="t-item">
          <div class="t-row"><b>{{ it.company }} · {{ it.position }}</b><span class="t-right">{{ it.period }}</span></div>
          <ul class="t-list"><li v-for="(p, i) in it.points" :key="i">{{ p }}</li></ul>
        </div>
      </section>
      <section v-if="content.projects.length" class="t-sec">
        <h2 class="t-title">> 项目</h2>
        <div v-for="p in content.projects" :key="p.name" class="t-item">
          <div class="t-row"><b>{{ p.name }}</b><span class="t-right">{{ p.period }}</span></div>
          <div class="t-tech"><span v-for="t in p.tech" :key="t" class="t-chip">{{ t }}</span></div>
          <ul class="t-list"><li v-for="(pt, i) in p.points" :key="i">{{ pt }}</li></ul>
        </div>
      </section>
      <section v-if="content.skills.length || content.certs.length" class="t-sec">
        <h2 class="t-title">> 技能栈</h2>
        <div v-for="s in content.skills" :key="s.group" class="t-item"><span class="t-chip t-chip-dark">{{ s.group }}</span> {{ s.items.join('、') }}</div>
        <div v-if="content.certs.length" class="t-item">证书：{{ content.certs.join('、') }}</div>
      </section>
    </div>
    </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ content: any; style: string }>()

const personal = computed(() => props.content?.personal || {})
const initial = computed(() => {
  const name = personal.value.name || '姓名'
  return name.charAt(0)
})
</script>

<style scoped>
/* A4 画布 */
.preview-wrap { background: #e8eaef; padding: 18px; border-radius: 8px; overflow: auto; }
.resume-sheet {
  width: 794px; min-height: 1123px; background: #fff; margin: 0 auto;
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.12); box-sizing: border-box;
}
/* 现代中文字体栈（优先大厂免费字体，回退系统字体）；数字等宽对齐 */
:root {
  --font-sans: 'HarmonyOS Sans SC', 'MiSans', 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', 'Helvetica Neue', sans-serif;
  --font-serif: 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'STSong', 'SimSun', serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace;
}
.resume-sheet { font-variant-numeric: tabular-nums; }
/* ---------- 简约现代 ---------- */
.sheet-modern { padding: 42px 46px; font-family: var(--font-sans); color: #2b2f36; }
.sheet-modern .m-header { display: flex; gap: 16px; align-items: center; border-bottom: 3px solid #2f6fed; padding-bottom: 18px; margin-bottom: 18px; }
.sheet-modern .m-avatar { width: 62px; height: 62px; border-radius: 50%; background: #2f6fed; color: #fff; font-size: 28px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex: none; }
.sheet-modern .m-name { font-size: 28px; font-weight: 800; letter-spacing: -0.02em; margin: 0; color: #16294f; }
.sheet-modern .m-position { font-size: 14px; font-weight: 500; letter-spacing: 0.06em; color: #2f6fed; margin: 3px 0 7px; }
.sheet-modern .m-contact { font-size: 12px; color: #6b7280; display: flex; flex-wrap: wrap; gap: 4px 16px; letter-spacing: 0.02em; }
.sheet-modern .m-sec { font-size: 14px; font-weight: 700; letter-spacing: 0.04em; color: #2f6fed; margin: 20px 0 8px; padding-bottom: 5px; border-bottom: 2px solid #2f6fed; }
.sheet-modern .m-item { margin-bottom: 10px; }
.sheet-modern .m-item-head { display: flex; justify-content: space-between; font-size: 13.5px; font-weight: 600; }
.sheet-modern .m-item-right { color: #6b7280; font-size: 11.5px; font-weight: 400; }
.sheet-modern .m-item-sub { font-size: 12px; color: #4b5563; margin: 2px 0; }
.sheet-modern .m-list { margin: 4px 0 0; padding-left: 18px; }
.sheet-modern .m-text, .sheet-modern .m-list li { font-size: 12.5px; line-height: 1.7; color: #374151; }
/* ---------- 经典专业 ---------- */
.sheet-classic { padding: 44px 52px; font-family: var(--font-serif); color: #222; }
.sheet-classic .c-header { text-align: center; border-bottom: 2px solid #333; padding-bottom: 14px; margin-bottom: 16px; }
.sheet-classic .c-name { font-size: 27px; font-weight: 700; letter-spacing: 0.16em; margin: 0; color: #1a1a1a; }
.sheet-classic .c-position { font-size: 13px; color: #444; margin-top: 5px; letter-spacing: 0.18em; }
.sheet-classic .c-contact { font-size: 11.5px; color: #555; margin-top: 8px; display: flex; justify-content: center; gap: 6px 18px; flex-wrap: wrap; }
.sheet-classic .c-sec { font-size: 14px; font-weight: 700; letter-spacing: 0.12em; margin: 18px 0 8px; border-bottom: 1px solid #999; padding-bottom: 4px; }
.sheet-classic .c-item { margin-bottom: 10px; }
.sheet-classic .c-row { display: flex; justify-content: space-between; font-size: 13.5px; font-weight: 600; }
.sheet-classic .c-right { color: #555; font-size: 11.5px; font-weight: 400; }
.sheet-classic .c-sub { font-size: 12.5px; color: #444; margin: 2px 0; }
.sheet-classic .c-list { margin: 4px 0 0; padding-left: 18px; }
.sheet-classic .c-text, .sheet-classic .c-list li { font-size: 12.5px; line-height: 1.8; color: #333; }
/* ---------- 创意活力 ---------- */
.sheet-creative { display: flex; min-height: 1123px; font-family: var(--font-sans); }
.sheet-creative .cr-side { width: 30%; background: linear-gradient(160deg, #4f6ef2, #7b5cf0); color: #fff; padding: 36px 22px; box-sizing: border-box; }
.sheet-creative .cr-avatar { width: 84px; height: 84px; border-radius: 50%; background: rgba(255, 255, 255, 0.22); border: 2px solid #fff; font-size: 36px; display: flex; align-items: center; justify-content: center; margin: 0 auto 12px; font-weight: 700; }
.sheet-creative .cr-name { text-align: center; font-size: 24px; font-weight: 800; letter-spacing: -0.01em; margin: 0; }
.sheet-creative .cr-pos { text-align: center; font-size: 12.5px; font-weight: 500; letter-spacing: 0.08em; opacity: 0.95; margin: 4px 0 18px; }
.sheet-creative .cr-block { margin-bottom: 18px; font-size: 12.5px; line-height: 1.8; }
.sheet-creative .cr-block-title { font-size: 12.5px; font-weight: 700; letter-spacing: 0.06em; border-bottom: 1px solid rgba(255, 255, 255, 0.4); padding-bottom: 4px; margin-bottom: 6px; }
.sheet-creative .cr-skill-name { font-weight: 600; margin-top: 6px; }
.sheet-creative .cr-skill-items { opacity: 0.92; }
.sheet-creative .cr-main { flex: 1; padding: 36px 30px; color: #2b2f36; }
.sheet-creative .cr-sec { font-size: 15px; font-weight: 700; letter-spacing: 0.03em; color: #4f6ef2; margin: 16px 0 8px; padding-left: 10px; border-left: 4px solid #4f6ef2; }
.sheet-creative .cr-item { margin-bottom: 10px; }
.sheet-creative .cr-row { display: flex; justify-content: space-between; font-size: 13.5px; font-weight: 600; }
.sheet-creative .cr-right { color: #6b7280; font-size: 11.5px; font-weight: 400; }
.sheet-creative .cr-sub { font-size: 12.5px; color: #4b5563; margin: 2px 0; }
.sheet-creative .cr-list { margin: 4px 0 0; padding-left: 18px; }
.sheet-creative .cr-text, .sheet-creative .cr-list li { font-size: 12.5px; line-height: 1.7; color: #374151; }
/* ---------- 极客技术 ---------- */
.sheet-tech { color: #e5e7eb; background: #0f172a; font-family: var(--font-sans); }
.sheet-tech .t-bar { background: #1e293b; padding: 28px 36px; display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #10b981; }
.sheet-tech .t-name { font-family: var(--font-mono); font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin: 0; color: #10b981; }
.sheet-tech .t-pos { font-size: 12.5px; font-weight: 500; letter-spacing: 0.08em; color: #94a3b8; margin-top: 4px; }
.sheet-tech .t-contact { font-size: 12px; color: #cbd5e1; text-align: right; line-height: 1.8; }
.sheet-tech .t-sec { padding: 14px 36px; }
.sheet-tech .t-title { font-family: var(--font-mono); font-size: 14px; font-weight: 700; letter-spacing: 0.02em; color: #10b981; margin: 10px 0 8px; }
.sheet-tech .t-row { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; margin: 6px 0; }
.sheet-tech .t-right { color: #94a3b8; }
.sheet-tech .t-text, .sheet-tech .t-list li { font-size: 12.5px; line-height: 1.7; color: #cbd5e1; }
.sheet-tech .t-list { margin: 4px 0; padding-left: 18px; }
.sheet-tech .t-tech { margin: 4px 0; }
.sheet-tech .t-chip { font-family: var(--font-mono); display: inline-block; background: #10b98122; color: #10b981; border: 1px solid #10b98155; border-radius: 4px; padding: 1px 8px; margin: 2px 4px 2px 0; font-size: 11.5px; }
.sheet-tech .t-chip-dark { background: #334155; color: #e2e8f0; border-color: #475569; }
</style>

<style>
/* 打印：只输出简历画布（A4） */
@media print {
  body * { visibility: hidden !important; }
  .resume-sheet, .resume-sheet * { visibility: visible !important; }
  .resume-sheet {
    position: absolute; left: 0; top: 0; width: 100%; box-shadow: none; margin: 0;
    /* 保留深色/渐变模板的背景色与分页完整性 */
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
  .resume-sheet .m-item, .resume-sheet .c-item, .resume-sheet .cr-item, .resume-sheet .t-item,
  .resume-sheet .m-sec, .resume-sheet .c-sec, .resume-sheet .cr-sec, .resume-sheet .t-sec {
    break-inside: avoid;
  }
  .preview-wrap { padding: 0; background: #fff; }
}
@page { size: A4; margin: 0; }
</style>
