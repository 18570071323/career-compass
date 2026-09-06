# 求职助手 · CareerCompass 网页端源码归档

「求职助手」是简历智配 SaaS 中面向求职者的功能模块（网页端），提供：

- **求职导航（问卷式职业规划）**：目标放第一位（直接就业 / 考研 / 考公考编），按目标动态出题——
  - 直接就业：岗位方向（按可职业化特长自动推荐）+ 已会技能 chips，以终为始补差距
  - 考研：本专业/跨考 + 预计考试时间 + 专业排名（保研判断）+ 科研竞赛
  - 考公/考编：国省事 + 报考窗口 + 政治面貌（先入党建议）+ 学生干部
  - 备考开始时间因人而异：按「距考试月数 × 每周可投入」给最晚启动建议
- **社招求职（有明确 JD）**：简历 × JD 匹配评分 + 五维报告 + 优化/改写
- **校招求职（无明确 JD）**：岗位库方向画像确定性打分与方向报告
- **新职业方向**：趋势职业/资格信息
- **公司避雷清单**：公司舆情/避雷信息
- 通用底座：免费池 / 次数包扣次、Web 管理后台发放次数包（流水对账）、免费捆绑与成本上限

> 本仓库为**网页端求职助手源码归档镜像**（Vue 页面 + 求职后端相关模块 + 文档）。
> 不含面向求职者的小程序源码、不含 B 端其余模块与业务路由、不含密钥与数据；
> **完整运行需与主项目集成**（Vue 应用外壳、FastAPI 全量应用、JD 岗位库种子等），相对导入与依赖以主项目为准。

## 目录结构

```
career-compass/
├── web-assistant/                # 网页端求职助手（Vue 3 + Element Plus）
│   └── src/
│       ├── pages/                # Candidate 页（5 个 tab）及其子页：求职导航 CareerPlan / 社招 / 校招 / 新职业 / 避雷
│       ├── components/           # 报告/雷达图/预览等组件
│       ├── api/client.ts         # 后端 API 客户端（含 candidate 求职端接口）
│       └── stores/auth.ts
├── backend/                      # 求职端后端（归档镜像）
│   ├── app/
│   │   ├── api/routes/           # candidate.py（求职助手路由）、mp_admin.py（次数包管理）等
│   │   ├── services/jobmatch/    # career_plan / direction / resume_analyze / report / seed …
│   │   ├── services/engine/      # DeepSeek 客户端 / 文档抽取 / 评分 / OCR
│   │   ├── models.py / schemas.py / config.py / db.py / services/auth.py
│   ├── tests/test_career_plan.py # 求职导航分支回归（无网络无 DB）
│   └── .env.example
├── docs/                         # 07 求职端规范 / 08 C端小程序方案 / 09 上线准备清单
└── README.md
```

## 回归测试（主分支逻辑）

```bash
cd backend
python tests/test_career_plan.py   # 目标三分类/入党/保研/启动建议文案等 7 例
```

## 说明与免责
- AI 引擎为 DeepSeek（OpenAI 兼容）；报告与规划仅供参考，不构成求职/备考承诺。
- 涉及小程序主体的微信认证/支付/类目讨论见 `docs/09`。
