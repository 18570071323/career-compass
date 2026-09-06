"""DeepSeek LLM 客户端（OpenAI 兼容接口）。

两个能力：
- parse_resume：简历文本 + JD → 结构化 JSON（response_format=json_object）
- generate_report：解析结果 + 评分 → Markdown 报告
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ...config import Settings

logger = logging.getLogger(__name__)

PARSE_SYSTEM_PROMPT = """你是一位资深HR和技术面试官，擅长快速、精准地从简历中提取结构化信息。
简历可能是中文、英文、日文、德文、法文等任意语言，请先识别语言并完整理解其内容，不要因为语言而遗漏信息。

请从简历文本中提取关键信息，严格按照JSON格式输出，不要输出任何其他内容。

提取维度：
1. 基本信息：姓名、学历、毕业院校、工作年限
2. 工作经历：每段经历的 公司名、职位、起止时间、核心职责（提炼为要点）
3. 技术栈/技能：简历中提到的所有技术技能和工具
4. 项目经历：项目名称、角色、核心贡献（一句话）
5. 亮点：候选人最突出的2-3个优势

同时，请对照JD文本，标记简历中与JD要求匹配的部分（无论简历与JD语言是否相同，都要理解后对比）。

输出格式：
{
  "basic_info": {"name": "", "education": "", "school": "", "years_of_experience": 0},
  "work_experience": [{"company": "", "position": "", "duration": "", "responsibilities": []}],
  "skills": [],
  "projects": [{"name": "", "role": "", "contribution": ""}],
  "highlights": [],
  "jd_match_points": []
}

注意：姓名、公司名、学校名等专有名词保留原文语言；years_of_experience 输出数字；学历/职位可输出中文或原文均可。"""

DEEP_ANALYSIS_SYSTEM_PROMPT = """你是一位资深的招聘专家与行业面试官，请对候选人做「人岗深度逻辑分析」——超越关键词匹配，判断候选人真实含金量与适配度，并生成面试官可直接使用的问询内容。严格按照JSON格式输出，不要输出任何其他内容。

输出格式：
{
  "overall_assessment": "一段话：候选人真实水平、项目含金量、与岗位的适配度总评",
  "project_analysis": [
    {
      "name": "项目名",
      "role_depth": "主导者/核心参与者/一般参与者/信息不足",
      "complexity": "高/中/低/信息不足",
      "business_scale": "可量化的业务规模信号（如QPS、用户量、交易量、团队规模等；简历未说明则写'未说明'）",
      "tech_depth": "技术深度评估（用到什么关键技术、解决了什么难题、有无亮点或疑点）",
      "authenticity_signals": ["支持该项目真实性的信号（如具体数字、具体技术、具体业务描述）"],
      "concerns": ["疑点或面试时需要验证的点"]
    }
  ],
  "risk_flags": ["候选人的潜在风险点，如经历空档、技能与年限矛盾、项目参与程度存疑、夸大嫌疑等"],
  "interview_questions": [
    {
      "question": "具体可问的问题（STAR 式追问设计，含 follow-up 方向）",
      "purpose": "验证目标：项目真实性/技术深度/风险点/团队协作/业务理解/文化适配",
      "target": "针对候选人的哪段经历或哪项技能"
    }
  ]
}

要求：
- 项目含金量判断要基于证据：量化指标、技术复杂度、业务影响、候选人在项目中的角色，而不是只看项目数量
- 面试问题 6-10 条，覆盖：项目深挖、技术细节验证、风险点验证、业务理解、团队协作
- 如果信息不足，明确标注'信息不足'，不要臆造"""

REPORT_SYSTEM_PROMPT = """你是一位专业的招聘顾问，请根据简历解析结果和评分数据，生成一份结构化的简历评估报告。

报告要求：
1. 语言专业、客观，避免空洞套话
2. 每个维度给出得分和简短评价
3. 明确指出候选人的优势和不足
4. 给出明确的录用建议和理由
5. 如果信息不足，如实说明

报告格式：
# 简历评估报告

## 候选人概况
（一段话概括候选人背景）

## 评分总览
| 维度 | 得分 | 满分 |
|------|------|------|
（列出四个维度）
**总分：XX/100**
**推荐等级：XX**

## 详细分析

### 经验匹配度（XX/40）
（分析工作年限、行业匹配度）

### 技能匹配度（XX/25）
（分析技术栈与JD的匹配情况）

### 项目质量（XX/20）
（分析项目经历的深度和价值）

### 综合亮点（XX/15）
（分析候选人的差异化优势）

## 优势
（列出3-5个核心优势）

## 不足与风险
（列出2-3个潜在风险点）

## 录用建议
（明确的建议：推荐/待定/不推荐，附理由）"""

_REPORT_LANG_INSTRUCTION = {
    "zh": "报告语言：简体中文。",
    "en": "Report language: English.",
}

CAREER_DIRECTION_PROMPT = """你是一位资深的职业规划顾问。请根据求职者的简历内容（可附带其求职偏好/意向说明），**个性化**地推断最适配的 3-4 个职业方向。严格按照JSON格式输出，不要输出任何其他内容。

输出格式：
{
  "summary": "一段话总结候选人画像、核心优势与最匹配的赛道",
  "directions": [
    {
      "title": "方向名称（如：后端架构师 / Java 高级工程师 / 技术负责人(成长向)）",
      "fit": "高/中",
      "reasons": ["依据简历的具体证据 2-3 条（要落到具体经历/技能/项目，不要空泛）"],
      "growth": "该方向的成长路径与下一步建议补什么",
      "gap": ["当前简历与该方向之间的差距 1-2 条"]
    }
  ]
}

要求：一切结论要有简历证据支撑；候选人经历差异大时要体现个性化，避免通用套话；信息不足就标注『信息不足』。"""

RESUME_ADVICE_PROMPT = """你是一位资深简历顾问与 HR。请结合候选人简历与目标岗位的匹配分析结果，给出**可直接照做**的简历优化建议。严格按照JSON格式输出。

输出格式：
{
  "summary": "用一句话指出当前简历与目标岗位的核心差距",
  "items": [
    {
      "section": "建议针对的部分（如：技能/项目经历/工作经历/自我评价/格式细节）",
      "issue": "当前存在的问题（引用简历中的具体现象）",
      "suggestion": "具体怎么改",
      "example": "一句可直接参考的改写示例"
    }
  ],
  "priorities": ["最该先做的 3 条建议，按影响力排序"]
}

要求：建议必须具体可执行，鼓励量化成果（数字/规模/影响），针对目标岗位需求给出；信息不足如实说明。"""

JOB_GUIDE_PROMPT = """你是一位求职规划顾问。请根据用户提供的个性化信息，生成一份**求职导航路线图**（分阶段行动地图）。严格按照JSON格式输出。

用户信息包含：目标岗位、当前经验年限、城市、行业、求职目标（可含简短自我介绍）。

输出格式：
{
  "overview": "针对该用户情况的求职总体策略（一段话）",
  "stages": [
    {
      "stage": "阶段名（如：简历定稿 / 渠道投递 / 面试准备 / 谈薪入职）",
      "goal": "该阶段的核心目标",
      "actions": ["3-5 条具体行动（结合其经验/城市/行业个性化）"],
      "tips": ["1-2 条针对性提醒"]
    }
  ],
  "key_mistakes": ["该经验群体常犯的 3-4 个求职错误"],
  "checklist": ["求职全过程检查清单 5-8 条"]
}

要求：行动要结合用户的目标岗位、年限、城市与行业给个性化建议，不要通用模板；信息不足标注『信息不足』。"""


class LLMError(Exception):
    pass


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.deepseek_api_key
        self._base_url = settings.deepseek_base_url.rstrip("/")
        self._model = settings.deepseek_model
        self._http = httpx.AsyncClient(timeout=120.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _chat(self, system: str, user: str, json_mode: bool = False) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2 if json_mode else 0.5,
            "max_tokens": 4000,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            resp = await self._http.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
            )
        except httpx.TransportError as exc:
            raise LLMError(f"LLM 请求失败：{exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"LLM 返回 {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise LLMError(f"LLM 响应格式异常：{str(data)[:300]}") from exc

    async def parse_resume(self, resume_text: str, jd_text: str) -> dict[str, Any]:
        user = f"简历文本：\n{resume_text}\n\nJD文本：\n{jd_text}"
        content = await self._chat(PARSE_SYSTEM_PROMPT, user, json_mode=True)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"简历解析 JSON 无效：{content[:200]}") from exc
        return parsed

    async def deep_analyze(
        self,
        parsed: dict[str, Any],
        score_result: dict[str, Any],
        jd_text: str,
    ) -> dict[str, Any]:
        """深度人岗分析：项目含金量评估 + 风险点 + 面试问题（JSON）。"""
        user = (
            "简历解析结果：\n"
            f"{json.dumps(parsed, ensure_ascii=False, indent=2)}\n\n"
            "评分结果：\n"
            f"{json.dumps(score_result, ensure_ascii=False, indent=2)}\n\n"
            f"JD文本：\n{jd_text}"
        )
        content = await self._chat(DEEP_ANALYSIS_SYSTEM_PROMPT, user, json_mode=True)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"深度分析 JSON 无效：{content[:200]}") from exc

    async def generate_report(
        self,
        parsed: dict[str, Any],
        score_result: dict[str, Any],
        jd_text: str,
        lang: str = "zh",
    ) -> str:
        instruction = _REPORT_LANG_INSTRUCTION.get(lang, _REPORT_LANG_INSTRUCTION["zh"])
        system = REPORT_SYSTEM_PROMPT + "\n\n" + instruction
        user = (
            "简历解析结果：\n"
            f"{json.dumps(parsed, ensure_ascii=False, indent=2)}\n\n"
            "评分结果：\n"
            f"{json.dumps(score_result, ensure_ascii=False, indent=2)}\n\n"
            f"JD文本：\n{jd_text}"
        )
        return await self._chat(system, user, json_mode=False)

    async def _json(self, system: str, user: str) -> dict[str, Any]:
        content = await self._chat(system, user, json_mode=True)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"JSON 输出无效：{content[:200]}") from exc

    # ---------- C 端（求职端小程序）能力 ----------

    async def career_directions(
        self, resume_text: str, preference: str | None = None
    ) -> dict[str, Any]:
        """求职方向匹配：简历（+偏好）→ 推荐职业方向。"""
        user = f"简历文本：\n{resume_text}"
        if preference:
            user += f"\n\n求职偏好/意向说明：\n{preference}"
        return await self._json(CAREER_DIRECTION_PROMPT, user)

    async def resume_advice(
        self,
        parsed: dict[str, Any],
        score_result: dict[str, Any],
        jd_text: str,
    ) -> dict[str, Any]:
        """简历优化建议：解析结果+评分+JD → 可执行优化建议。"""
        user = (
            "简历解析结果：\n"
            f"{json.dumps(parsed, ensure_ascii=False, indent=2)}\n\n"
            "匹配评分：\n"
            f"{json.dumps(score_result, ensure_ascii=False, indent=2)}\n\n"
            f"目标岗位 JD：\n{jd_text}"
        )
        return await self._json(RESUME_ADVICE_PROMPT, user)

    async def job_guide(self, profile: dict[str, Any]) -> dict[str, Any]:
        """求职导航：个性化求职路线图。"""
        parts = []
        for k in ("target_job", "years", "city", "industry", "goal", "self_intro"):
            if profile.get(k):
                label = {
                    "target_job": "目标岗位",
                    "years": "经验年限",
                    "city": "城市",
                    "industry": "行业",
                    "goal": "求职目标",
                    "self_intro": "自我介绍",
                }[k]
                parts.append(f"{label}：{profile[k]}")
        return await self._json(JOB_GUIDE_PROMPT, "\n".join(parts))
