"""岗位库种子数据（docs/07-§4，M7.1）。

幂等：库内已有岗位则跳过；`python -m app.services.jobmatch.seed` 可强制重灌（force=1）。
懒加载：推荐/岗位库接口发现库为空时自动调用 seed_all。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import SessionLocal
from ...models import (
    CertScarcity,
    JdCategory,
    JdLibrary,
    JdSkillOntology,
    Recommendation,
    ToolchainTemplate,
)
from .matching import load_ontology, scan_certs, scan_skills
from .tokenize import add_words

logger = logging.getLogger(__name__)

# ---------- 分类树 ----------

INDUSTRIES = ["互联网", "金融", "快消", "制造业", "咨询", "专业服务"]

FUNCTION_TREE: dict[str, list[str]] = {
    "技术": ["前端开发", "后端开发", "算法工程师", "数据分析", "测试", "运维"],
    "产品": ["产品经理"],
    "运营": ["用户运营", "内容运营", "电商运营", "新媒体运营"],
    "市场": ["市场营销", "品牌公关", "市场推广"],
    "职能": ["人力资源", "财务", "法务", "行政"],
    "金融综合": ["综合柜员", "客户经理助理", "运营支持", "管理培训生"],
}

# ---------- 技能本体 ----------

SKILL_ONTOLOGY: list[tuple[str, list[str], str, bool]] = [
    # (规范名, 别名, 类别, 是否默认核心)
    ("Python", ["py", "python3"], "tech", True),
    ("Java", ["java8", "java ee"], "tech", True),
    ("C++", ["cpp", "c/c++", "c plus plus"], "tech", False),
    ("C", [], "tech", False),
    ("Go", ["golang"], "tech", False),
    ("JavaScript", ["js", "es6"], "tech", True),
    ("TypeScript", ["ts"], "tech", False),
    ("SQL", ["mysql", "postgresql", "oracle sql", "数据库"], "tech", True),
    ("R", [], "tech", False),
    ("Shell", ["bash"], "tech", False),
    ("PHP", [], "tech", False),
    ("HTML", ["html5"], "tech", False),
    ("CSS", ["css3"], "tech", False),
    ("Vue", ["vue3", "vue.js", "vue2"], "tech", False),
    ("React", ["react.js", "reactjs"], "tech", False),
    ("Node.js", ["node", "nodejs"], "tech", False),
    ("Webpack", [], "tech", False),
    ("Vite", [], "tech", False),
    ("小程序", ["微信小程序", "uniapp"], "tech", False),
    ("ECharts", [], "tech", False),
    ("three.js", ["threejs", "webgl"], "tech", False),
    ("Spring", ["spring boot", "springboot", "spring cloud", "springmvc"], "tech", True),
    ("Django", [], "tech", False),
    ("Flask", [], "tech", False),
    ("FastAPI", [], "tech", False),
    ("MyBatis", [], "tech", False),
    ("Redis", [], "tech", True),
    ("MySQL", ["mysql数据库"], "tech", True),
    ("PostgreSQL", ["pg"], "tech", False),
    ("MongoDB", ["mongo"], "tech", False),
    ("Kafka", [], "tech", False),
    ("RabbitMQ", [], "tech", False),
    ("消息队列", ["mq", "消息中间件"], "tech", False),
    ("Docker", [], "tech", False),
    ("Kubernetes", ["k8s", "k8"], "tech", False),
    ("Linux", [], "tech", False),
    ("Nginx", [], "tech", False),
    ("微服务", ["微服务架构"], "tech", False),
    ("分布式", ["分布式系统"], "tech", False),
    ("Git", ["github", "gitlab"], "tech", False),
    ("机器学习", ["ml", "机器学习算法"], "analysis", True),
    ("深度学习", ["dl"], "analysis", False),
    ("PyTorch", ["torch"], "analysis", True),
    ("TensorFlow", ["tf"], "analysis", False),
    ("NLP", ["自然语言处理"], "analysis", False),
    ("计算机视觉", ["cv", "机器视觉"], "analysis", False),
    ("推荐系统", [], "analysis", False),
    ("数据挖掘", [], "analysis", False),
    ("数据分析", ["数据分析能力"], "analysis", True),
    ("数据可视化", ["可视化"], "analysis", False),
    ("统计学", ["统计", "统计方法"], "analysis", False),
    ("A/B测试", ["ab测试", "ab实验", "实验设计"], "analysis", False),
    ("Spark", [], "analysis", False),
    ("Hadoop", [], "analysis", False),
    ("Hive", [], "analysis", False),
    ("ETL", [], "analysis", False),
    ("数据仓库", ["数仓"], "analysis", False),
    ("特征工程", [], "analysis", False),
    ("大模型", ["llm", "大语言模型", "transformer"], "analysis", False),
    ("强化学习", ["rl"], "analysis", False),
    ("Excel", [], "analysis", True),
    ("Tableau", [], "analysis", False),
    ("PowerBI", ["power bi"], "analysis", False),
    ("BI", ["商业智能"], "analysis", False),
    ("需求分析", [], "product", True),
    ("原型设计", ["原型"], "product", True),
    ("Axure", [], "product", False),
    ("Figma", [], "product", False),
    ("用户调研", ["用户研究"], "product", False),
    ("竞品分析", [], "product", False),
    ("PRD", ["需求文档"], "product", False),
    ("项目管理", ["项目推进"], "product", False),
    ("敏捷", ["scrum"], "product", False),
    ("用户画像", [], "product", False),
    ("指标体系", ["指标体系建设", "指标体系搭建"], "product", False),
    ("用户运营", [], "oper", True),
    ("内容运营", [], "oper", False),
    ("活动策划", ["活动执行"], "oper", True),
    ("社群运营", [], "oper", False),
    ("新媒体", ["新媒体运营", "双微"], "oper", False),
    ("增长", ["用户增长"], "oper", False),
    ("私域", ["私域运营"], "oper", False),
    ("转化率", ["转化"], "oper", False),
    ("SEO", [], "oper", False),
    ("直播运营", ["直播"], "oper", False),
    ("电商运营", ["店铺运营", "电商平台"], "oper", False),
    ("市场营销", ["营销", "市场"], "market", True),
    ("品牌", ["品牌营销"], "market", False),
    ("广告投放", ["投放", "信息流"], "market", False),
    ("内容营销", [], "market", False),
    ("媒介", [], "market", False),
    ("公关", ["媒体关系"], "market", False),
    ("渠道", ["渠道推广"], "market", False),
    ("文案", ["文案能力", "写作"], "market", False),
    ("HR", ["人力资源"], "func", True),
    ("招聘", ["校园招聘", "社会招聘"], "func", False),
    ("培训", [], "func", False),
    ("绩效管理", ["绩效"], "func", False),
    ("薪酬", ["薪酬管理"], "func", False),
    ("员工关系", [], "func", False),
    ("财务分析", ["经营分析"], "func", True),
    ("预算", ["预算管理"], "func", False),
    ("税务", ["税务申报"], "func", False),
    ("会计", ["会计核算", "财务核算"], "func", False),
    ("审计", [], "func", False),
    ("法务", [], "func", False),
    ("合同", ["合同审核", "合同管理"], "func", False),
    ("合规", [], "func", False),
    ("法律", [], "func", False),
    ("行政", ["行政管理"], "func", False),
    ("办公软件", ["office"], "soft", False),
    ("PPT", ["演示文稿"], "soft", False),
    ("Word", [], "soft", False),
    ("英语", ["英语读写", "英语六级"], "soft", False),
]

# ---------- 证书稀缺度 ----------

CERT_SCARCITY: list[tuple[str, list[str], int, str]] = [
    ("CPA", ["注册会计师", "cpa证书"], 5, "S"),
    ("CFA三级", ["cfa level 3", "cfa l3", "cfa 三级"], 5, "S"),
    ("FRM二级", ["frm level 2", "frm l2", "frm 二级"], 5, "S"),
    ("精算师", ["soa", "精算"], 5, "S"),
    ("CFA一级", ["cfa level 1", "cfa l1", "cfa 一级"], 4, "A"),
    ("FRM一级", ["frm level 1", "frm l1", "frm 一级"], 4, "A"),
    ("ACCA", [], 4, "A"),
    ("法律职业资格", ["法考", "司法考试"], 4, "A"),
    ("保荐代表人", [], 4, "A"),
    ("PMP", [], 3, "B"),
    ("软考", ["软考中级", "系统集成项目管理"], 3, "B"),
    ("二级口译", ["catti", "翻译资格"], 3, "B"),
    ("中级会计", ["中级会计师"], 3, "B"),
    ("证券从业资格", ["证券从业"], 1, "C"),
    ("初级会计", ["初级会计证", "初级会计师"], 1, "C"),
    ("大学英语四级", ["cet-4", "cet4", "英语四级"], 1, "C"),
    ("大学英语六级", ["cet-6", "cet6", "英语六级"], 1, "C"),
    ("计算机二级", [], 1, "C"),
    ("普通话", ["普通话证书"], 1, "C"),
    ("教师资格证", ["教资"], 1, "C"),
]

# ---------- 工具链模板 ----------

TOOLCHAIN_TEMPLATES: dict[str, list[str]] = {
    "前端开发": ["JavaScript", "TypeScript", "HTML", "CSS", "Vue", "React", "Git", "Webpack"],
    "后端开发": ["Java", "Spring", "MySQL", "Redis", "Linux", "Docker", "Git", "消息队列"],
    "算法工程师": ["Python", "机器学习", "深度学习", "PyTorch", "SQL", "数据分析", "统计学"],
    "数据分析": ["SQL", "Python", "Excel", "数据可视化", "统计学", "数据分析"],
    "测试": ["Python", "SQL", "Linux", "Git"],
    "运维": ["Linux", "Shell", "Docker", "Kubernetes", "Python", "Git"],
    "产品经理": ["需求分析", "原型设计", "用户调研", "竞品分析", "数据分析", "Axure"],
    "用户运营": ["用户运营", "活动策划", "数据分析", "Excel", "文案"],
    "内容运营": ["内容运营", "文案", "数据分析", "Excel", "新媒体"],
    "电商运营": ["电商运营", "Excel", "数据分析", "文案", "活动策划"],
    "新媒体运营": ["新媒体", "文案", "数据分析", "内容运营", "Excel"],
    "市场营销": ["市场营销", "品牌", "数据分析", "Excel", "用户画像", "文案"],
    "品牌公关": ["品牌", "公关", "文案", "内容营销", "媒介"],
    "市场推广": ["市场营销", "渠道", "数据分析", "Excel", "文案"],
    "人力资源": ["HR", "招聘", "培训", "绩效管理", "Excel"],
    "财务": ["财务分析", "会计", "预算", "税务", "Excel"],
    "法务": ["法务", "合同", "合规"],
    "行政": ["行政", "Excel", "文案"],
}

# ---------- 种子岗位（约 70 条，覆盖 5 大职能类别 × 多行业） ----------
# 字段：company, industry, category, title, city, education, salary, certs, responsibilities, requirements

JD_SEEDS: list[dict] = [
    # ============ 技术-前端 ============
    {"company": "云启科技", "industry": "互联网", "category": "前端开发", "title": "前端开发工程师", "city": "北京", "education": "本科及以上", "salary": "15-25K", "certs": [],
     "resp": ["负责 Web 应用前端开发与功能迭代", "与产品、设计协作高质量还原交互界面", "参与前端组件库建设与维护", "负责页面性能优化与兼容性适配"],
     "req": ["计算机相关专业本科及以上", "熟悉 HTML/CSS/JavaScript，掌握 Vue 或 React", "了解 TypeScript，有 Vite/Webpack 工程化经验", "熟悉 Git 协作流程", "有实习项目经验者优先"]},
    {"company": "星图金融", "industry": "金融", "category": "前端开发", "title": "前端开发工程师（金融科技）", "city": "上海", "education": "本科及以上", "salary": "18-28K", "certs": [],
     "resp": ["金融业务系统前端开发与维护", "数据可视化大屏与报表组件开发", "交易流程表单与权限组件开发", "前端性能与安全加固"],
     "req": ["本科及以上，计算机相关专业", "扎实的 JavaScript/TypeScript 基础", "熟悉 Vue3，了解 React", "熟悉 ECharts 数据可视化", "了解 HTTP 协议与浏览器原理", "有 Node.js 经验加分"]},
    {"company": "探路者咨询", "industry": "咨询", "category": "前端开发", "title": "前端开发实习生", "city": "北京", "education": "本科及以上", "salary": "200-250/天", "certs": [],
     "resp": ["协助咨询项目数据看板前端开发", "参与通用组件开发与单元测试", "配合后端完成接口联调"],
     "req": ["本科及以上在校生，每周实习 4 天以上", "HTML/CSS/JavaScript 基础扎实", "了解 Vue 或 React", "有作品或实习经历加分"]},
    {"company": "智造云", "industry": "制造业", "category": "前端开发", "title": "前端开发工程师", "city": "深圳", "education": "本科及以上", "salary": "14-22K", "certs": [],
     "resp": ["工业互联网平台前端开发", "设备监控可视化页面开发（3D 方向加分）", "移动端 H5 适配与优化"],
     "req": ["本科及以上，计算机相关专业", "JavaScript/TypeScript 基础扎实，熟悉 Vue 或 React", "熟悉浏览器兼容与移动端适配", "有 ECharts/three.js 经验者优先", "有工业/物联网项目经验加分"]},
    {"company": "快享", "industry": "快消", "category": "前端开发", "title": "电商前端开发工程师", "city": "杭州", "education": "本科及以上", "salary": "16-24K", "certs": [],
     "resp": ["电商大促活动页与 H5 页面开发", "营销组件化与动态化搭建", "页面性能监控与优化"],
     "req": ["本科及以上，计算机相关专业", "JavaScript/TypeScript 扎实，熟悉 Vue3", "有小程序开发经验优先", "了解 Node.js 与工程化工具", "有电商活动页经验优先"]},
    {"company": "星辰互动", "industry": "互联网", "category": "前端开发", "title": "Web 前端开发工程师", "city": "广州", "education": "本科及以上", "salary": "13-20K", "certs": [],
     "resp": ["官网与内部中台前端开发", "前端组件库建设与维护", "与后端协作完成接口联调"],
     "req": ["计算机相关专业本科及以上", "JavaScript/TypeScript/HTML/CSS 基础扎实", "熟悉 React 或 Vue", "熟悉 Git，了解 HTTP", "有实习或开源项目经验优先"]},
    # ============ 技术-后端 ============
    {"company": "云启科技", "industry": "互联网", "category": "后端开发", "title": "Java 后端开发工程师", "city": "北京", "education": "本科及以上", "salary": "20-30K", "certs": [],
     "resp": ["核心业务服务设计与开发", "高并发接口与数据一致性保障", "数据库表设计与查询优化", "参与微服务治理与链路监控"],
     "req": ["本科及以上，计算机相关专业", "Java 基础扎实，熟悉 Spring Boot/Spring Cloud", "熟悉 MySQL、Redis，了解消息队列（Kafka/RabbitMQ）", "熟悉 Linux 常用命令", "有分布式系统经验优先", "有实习或开源项目优先"]},
    {"company": "星图金融", "industry": "金融", "category": "后端开发", "title": "Java 后端开发工程师（风控）", "city": "上海", "education": "硕士及以上", "salary": "22-32K", "certs": [],
     "resp": ["风控决策引擎与规则引擎开发", "特征计算与风控接口开发", "接口性能优化与稳定性保障", "与算法团队协作落地模型服务"],
     "req": ["硕士及以上，计算机/金融科技相关专业", "Java 基础扎实，熟悉 Spring 生态", "熟悉 MySQL、Redis", "了解分布式事务与高可用架构", "有金融风控项目经验优先"]},
    {"company": "智造云", "industry": "制造业", "category": "后端开发", "title": "Go 后端开发工程师", "city": "深圳", "education": "本科及以上", "salary": "18-26K", "certs": [],
     "resp": ["物联网平台后端开发", "设备接入网关与消息处理", "数据服务接口开发与性能调优"],
     "req": ["本科及以上，计算机相关专业", "熟悉 Go 或 Java，Go 优先", "熟悉 MySQL、Redis", "熟悉 TCP/HTTP 协议", "有 MQTT/Kafka 经验优先"]},
    {"company": "途行", "industry": "互联网", "category": "后端开发", "title": "Python 后端开发工程师", "city": "上海", "education": "本科及以上", "salary": "17-25K", "certs": [],
     "resp": ["推荐服务与数据处理服务后端开发", "接口开发与部署", "数据管道与异步任务开发"],
     "req": ["本科及以上，计算机相关专业", "Python 基础扎实，熟悉 FastAPI/Flask/Django", "熟悉 MySQL/PostgreSQL 与 Redis", "了解 Docker 与 CI/CD", "有爬虫或数据处理经验加分"]},
    {"company": "快享", "industry": "快消", "category": "后端开发", "title": "后端开发工程师（订单系统）", "city": "杭州", "education": "本科及以上", "salary": "18-26K", "certs": [],
     "resp": ["订单/库存核心系统开发", "高可用架构设计与容灾演练", "链路监控与性能优化"],
     "req": ["本科及以上，计算机相关专业", "Java 基础扎实，熟悉 Spring Boot", "熟悉 MySQL、Redis 与消息队列", "具备分布式系统基础知识", "有电商系统实习经验优先"]},
    {"company": "中科数联", "industry": "咨询", "category": "后端开发", "title": "后端开发工程师（数据平台）", "city": "北京", "education": "本科及以上", "salary": "20-28K", "certs": [],
     "resp": ["数据平台后端服务开发", "ETL 调度与数据服务 API 开发", "数据质量与稳定性保障"],
     "req": ["本科及以上，计算机相关专业", "熟悉 Java 或 Python", "SQL 熟练，了解数据仓库建模", "有 Hadoop/Spark 经验加分", "熟悉 Linux 与 Shell"]},
    # ============ 技术-算法 ============
    {"company": "云启科技", "industry": "互联网", "category": "算法工程师", "title": "推荐算法工程师", "city": "北京", "education": "硕士及以上", "salary": "25-40K", "certs": [],
     "resp": ["推荐系统召回/排序模型优化", "特征工程与样本构建", "A/B 实验设计与效果评估", "模型上线与监控"],
     "req": ["硕士及以上，计算机/数学相关专业", "机器学习/深度学习基础扎实", "熟悉 Python 与 PyTorch/TensorFlow", "熟悉 SQL/Spark 数据处理", "有推荐系统或论文发表经验优先"]},
    {"company": "星图金融", "industry": "金融", "category": "算法工程师", "title": "量化算法工程师", "city": "上海", "education": "硕士及以上", "salary": "30-45K", "certs": ["CFA一级", "FRM一级"],
     "resp": ["量化策略研究与因子挖掘", "回测系统开发与优化", "风险模型与组合优化"],
     "req": ["硕士及以上，数学/统计/计算机专业", "Python 熟练，熟悉机器学习", "有金融工程或量化实习经验优先", "通过 CFA/FRM 加分", "数学建模竞赛获奖优先"]},
    {"company": "智造云", "industry": "制造业", "category": "算法工程师", "title": "机器视觉算法工程师", "city": "深圳", "education": "硕士及以上", "salary": "22-35K", "certs": [],
     "resp": ["工业质检视觉算法研发", "目标检测/分割模型训练与调优", "模型部署与边缘端优化"],
     "req": ["硕士及以上，计算机/自动化相关专业", "熟悉计算机视觉与深度学习", "熟悉 PyTorch，了解 OpenCV", "熟悉 Python 或 C++", "有工业视觉落地项目优先"]},
    {"company": "途行", "industry": "互联网", "category": "算法工程师", "title": "NLP 算法工程师（大模型方向）", "city": "上海", "education": "硕士及以上", "salary": "28-45K", "certs": [],
     "resp": ["大模型微调与 Prompt 工程", "RAG 检索增强系统开发", "模型效果评估与数据构造"],
     "req": ["硕士及以上，计算机相关专业", "NLP 基础扎实，熟悉 Transformer 架构", "熟悉 Python 与 PyTorch", "了解 Llama 等开源大模型", "有 LLM 项目或论文发表经验优先"]},
    {"company": "数澜智能", "industry": "互联网", "category": "算法工程师", "title": "数据挖掘算法工程师", "city": "杭州", "education": "本科及以上", "salary": "20-30K", "certs": [],
     "resp": ["用户画像与标签挖掘", "行为序列建模与特征平台建设", "模型效果分析与迭代"],
     "req": ["本科及以上，计算机/数学相关专业", "机器学习基础扎实", "熟悉 Python、SQL", "熟悉 Spark/Hadoop 大数据栈", "有数据挖掘项目经验优先"]},
    # ============ 技术-数据分析 ============
    {"company": "云启科技", "industry": "互联网", "category": "数据分析", "title": "数据分析师", "city": "北京", "education": "本科及以上", "salary": "15-25K", "certs": [],
     "resp": ["业务指标体系搭建与维护", "专题分析与归因分析", "A/B 实验设计与结果分析", "报表自动化与数据看板"],
     "req": ["本科及以上，统计/数学/计算机相关专业", "SQL 熟练，Python（pandas）熟练", "统计学基础扎实", "熟悉 Excel 与数据可视化（Tableau/BI）", "有 A/B 实验经验优先"]},
    {"company": "快享", "industry": "快消", "category": "数据分析", "title": "电商数据分析师", "city": "杭州", "education": "本科及以上", "salary": "14-22K", "certs": [],
     "resp": ["电商经营数据分析与日报输出", "大促活动效果评估", "用户增长与转化分析", "搭建经营分析看板"],
     "req": ["本科及以上，统计/经济/计算机相关专业", "SQL 熟练，Excel 熟练", "熟悉 Python 或 R 数据分析", "了解电商业务指标体系", "有数据可视化经验优先"]},
    {"company": "星图金融", "industry": "金融", "category": "数据分析", "title": "数据分析师（风控）", "city": "上海", "education": "本科及以上", "salary": "18-26K", "certs": [],
     "resp": ["信贷风控数据分析与监控", "策略变量分析与报告输出", "风控模型监控报表开发"],
     "req": ["本科及以上，统计/金融/数学相关专业", "SQL 熟练，Python 熟练", "统计学基础扎实", "了解风控业务优先", "表达清晰，具备报告撰写能力"]},
    {"company": "探路者咨询", "industry": "咨询", "category": "数据分析", "title": "数据分析助理（应届）", "city": "北京", "education": "本科及以上", "salary": "12-18K", "certs": [],
     "resp": ["咨询项目数据分析与处理", "市场调研数据处理与清洗", "图表与报告制作"],
     "req": ["本科及以上，统计/经济/管理相关专业", "Excel 熟练，掌握 SQL 或 Python", "逻辑清晰，PPT 制作能力强", "有调研项目经验优先"]},
    {"company": "途行", "industry": "互联网", "category": "数据分析", "title": "数据分析师（增长方向）", "city": "上海", "education": "本科及以上", "salary": "15-23K", "certs": [],
     "resp": ["增长漏斗与用户行为分析", "实验设计与评估", "数据产品需求提炼与落地"],
     "req": ["本科及以上，统计/数学/计算机相关专业", "SQL、Python 熟练", "统计学基础扎实，了解 A/B 实验", "熟悉数据可视化工具", "有增长分析实习经验优先"]},
    # ============ 技术-测试/运维 ============
    {"company": "云启科技", "industry": "互联网", "category": "测试", "title": "测试开发工程师", "city": "北京", "education": "本科及以上", "salary": "15-22K", "certs": [],
     "resp": ["自动化测试框架搭建与维护", "接口测试与性能测试", "质量保障流程建设"],
     "req": ["本科及以上，计算机相关专业", "Python 或 Java 基础扎实", "了解 Selenium/Appium 等测试工具", "熟悉 SQL 与 Linux", "计算机基础扎实，了解网络协议"]},
    {"company": "星图金融", "industry": "金融", "category": "测试", "title": "软件测试工程师", "city": "上海", "education": "本科及以上", "salary": "13-19K", "certs": [],
     "resp": ["功能测试用例设计与执行", "接口测试与缺陷管理", "回归测试与质量报告"],
     "req": ["本科及以上，计算机相关专业", "掌握测试理论与流程", "熟悉 SQL，了解 Python", "细致负责，文档能力强", "有金融系统测试经验优先"]},
    {"company": "云启科技", "industry": "互联网", "category": "运维", "title": "运维开发工程师", "city": "北京", "education": "本科及以上", "salary": "16-24K", "certs": [],
     "resp": ["容器平台与 CI/CD 建设", "监控告警体系搭建", "线上故障处理与复盘"],
     "req": ["本科及以上，计算机相关专业", "熟悉 Linux 与 Shell", "熟悉 Docker/Kubernetes", "了解 Prometheus/Grafana", "Python 或 Go 基础加分"]},
    {"company": "途行", "industry": "互联网", "category": "运维", "title": "SRE 工程师（校招）", "city": "上海", "education": "本科及以上", "salary": "15-22K", "certs": [],
     "resp": ["服务稳定性保障与容量规划", "自动化运维工具开发", "故障响应与应急预案"],
     "req": ["本科及以上，计算机相关专业", "Linux 与网络基础扎实", "熟悉 Shell/Python", "了解 Docker/Kubernetes", "有运维或 SRE 实习经验优先"]},
    # ============ 产品 ============
    {"company": "云启科技", "industry": "互联网", "category": "产品经理", "title": "产品经理（校招）", "city": "北京", "education": "本科及以上", "salary": "15-22K", "certs": [],
     "resp": ["需求调研与 PRD 撰写", "竞品分析与用户研究", "数据驱动的功能迭代", "跨团队协同推进项目"],
     "req": ["本科及以上，专业不限", "逻辑清晰，表达能力强", "掌握需求分析与原型设计，熟悉 Axure/Figma", "有用户调研与数据分析基础", "有产品实习经验优先"]},
    {"company": "途行", "industry": "互联网", "category": "产品经理", "title": "产品经理（增长方向）", "city": "上海", "education": "本科及以上", "salary": "14-21K", "certs": [],
     "resp": ["增长产品功能设计", "A/B 实验设计与分析", "用户转化漏斗优化", "数据驱动的产品决策"],
     "req": ["本科及以上，专业不限", "具备产品思维与数据敏感度", "了解 A/B 实验方法论", "掌握原型设计与用户调研方法", "有增长或电商实习经验优先"]},
    {"company": "星图金融", "industry": "金融", "category": "产品经理", "title": "金融产品经理（应届）", "city": "上海", "education": "硕士及以上", "salary": "18-26K", "certs": [],
     "resp": ["金融产品需求分析与方案设计", "竞品与监管政策研究", "与风控、研发团队协同落地", "产品数据跟踪与迭代"],
     "req": ["硕士及以上，金融/经济相关专业优先", "掌握需求分析与原型设计", "了解银行/信贷业务加分", "沟通协调能力强，文档规范", "有金融实习经验优先"]},
    {"company": "快享", "industry": "快消", "category": "产品经理", "title": "电商产品经理", "city": "杭州", "education": "本科及以上", "salary": "14-22K", "certs": [],
     "resp": ["电商交易流程产品设计", "商家端与用户端需求分析", "数据分析驱动优化", "跨部门协同推进"],
     "req": ["本科及以上，专业不限", "掌握需求分析与原型设计", "有用户调研与数据分析基础", "了解电商业务优先", "有产品实习经验优先"]},
    {"company": "智造云", "industry": "制造业", "category": "产品经理", "title": "工业软件产品经理", "city": "深圳", "education": "本科及以上", "salary": "15-23K", "certs": [],
     "resp": ["工业软件需求分析与方案设计", "竞品调研与行业研究", "产品文档与项目推进"],
     "req": ["本科及以上，工科背景优先", "掌握需求分析与原型设计", "逻辑清晰，文档能力强", "了解工业软件/MES/ERP 加分", "有产品实习经验优先"]},
    {"company": "探路者咨询", "industry": "咨询", "category": "产品经理", "title": "产品经理助理（数字化转型）", "city": "北京", "education": "本科及以上", "salary": "13-19K", "certs": [],
     "resp": ["客户数字化转型需求梳理", "解决方案文档撰写", "项目进度跟进与协调"],
     "req": ["本科及以上，管理/计算机相关专业", "逻辑清晰，PPT 与文档能力强", "掌握需求分析方法", "有咨询或项目实习经验优先", "抗压能力强"]},
    {"company": "数澜智能", "industry": "互联网", "category": "产品经理", "title": "数据产品经理（校招）", "city": "杭州", "education": "本科及以上", "salary": "15-23K", "certs": [],
     "resp": ["数据产品功能设计", "指标字典与数据规范维护", "数据可视化方案设计", "需求调研与竞品分析"],
     "req": ["本科及以上，统计/计算机相关专业", "具备数据分析基础，了解 SQL", "掌握需求分析与原型设计", "逻辑清晰，沟通能力强", "有数据分析或数据产品实习优先"]},
    {"company": "星辰互动", "industry": "互联网", "category": "产品经理", "title": "内容产品经理", "city": "广州", "education": "本科及以上", "salary": "13-20K", "certs": [],
     "resp": ["内容社区产品功能设计", "内容策略与运营机制设计", "用户调研与数据复盘"],
     "req": ["本科及以上，专业不限", "产品基础扎实，有内容产品实习优先", "掌握原型设计与用户调研", "具备数据分析能力", "对社区产品有理解"]},
    {"company": "中科数联", "industry": "咨询", "category": "产品经理", "title": "平台产品经理", "city": "北京", "education": "本科及以上", "salary": "16-24K", "certs": [],
     "resp": ["B 端平台产品规划与设计", "客户需求分析与方案输出", "产品交付协同与跟进"],
     "req": ["本科及以上，专业不限", "掌握需求分析与原型设计", "文档能力强，逻辑清晰", "有 B 端产品实习优先", "沟通与推动力强"]},
    {"company": "元启智能", "industry": "互联网", "category": "产品经理", "title": "AI 产品经理（校招）", "city": "深圳", "education": "硕士及以上", "salary": "20-30K", "certs": [],
     "resp": ["AI 应用产品需求分析与设计", "大模型应用场景调研", "PRD 撰写与效果评估"],
     "req": ["硕士及以上，理工科背景优先", "了解大模型应用与 Prompt 工程", "掌握需求分析与原型设计", "学习能力强，逻辑清晰", "有 AI 产品实习经验优先"]},
    # ============ 运营-用户运营 ============
    {"company": "快享", "industry": "快消", "category": "用户运营", "title": "用户运营专员（校招）", "city": "杭州", "education": "本科及以上", "salary": "10-15K", "certs": [],
     "resp": ["用户分层与生命周期运营", "用户策略制定与执行", "活动策划与落地", "运营数据分析与复盘"],
     "req": ["本科及以上，专业不限", "掌握用户运营方法论", "有活动策划与执行经验", "数据分析能力（Excel）", "文案能力强，快消/电商实习优先"]},
    {"company": "途行", "industry": "互联网", "category": "用户运营", "title": "用户运营（增长）", "city": "上海", "education": "本科及以上", "salary": "11-16K", "certs": [],
     "resp": ["拉新与留存策略制定", "A/B 实验与效果复盘", "社群运营与用户触达", "运营数据报表输出"],
     "req": ["本科及以上，专业不限", "具备增长思维与数据敏感度", "有社群运营经验", "文案与活动策划能力", "自驱力强，结果导向"]},
    {"company": "星辰互动", "industry": "互联网", "category": "用户运营", "title": "用户运营专员", "city": "广州", "education": "本科及以上", "salary": "10-15K", "certs": [],
     "resp": ["用户体系与会员运营", "用户活动策划与执行", "用户反馈收集与分析"],
     "req": ["本科及以上，专业不限", "掌握用户运营基础方法", "有活动策划经验", "数据分析能力（Excel）", "具备同理心与沟通能力"]},
    {"company": "元启智能", "industry": "互联网", "category": "用户运营", "title": "用户运营（社区方向）", "city": "深圳", "education": "本科及以上", "salary": "12-17K", "certs": [],
     "resp": ["社区用户增长与活跃运营", "内容话题与活动策划", "社区数据分析与复盘"],
     "req": ["本科及以上，专业不限", "有社区运营经验优先", "活动策划与文案能力强", "数据分析基础扎实", "网感好，了解年轻用户"]},
    # ============ 运营-内容运营 ============
    {"company": "星辰互动", "industry": "互联网", "category": "内容运营", "title": "内容运营（校招）", "city": "广州", "education": "本科及以上", "salary": "9-14K", "certs": [],
     "resp": ["内容选题与创作", "内容审核与分发", "内容数据复盘与优化", "用户互动维护"],
     "req": ["本科及以上，专业不限", "文案能力强，内容敏感度高", "具备数据分析基础", "有自媒体经验加分", "责任心强"]},
    {"company": "快享", "industry": "快消", "category": "内容运营", "title": "内容运营（电商）", "city": "杭州", "education": "本科及以上", "salary": "10-15K", "certs": [],
     "resp": ["商品内容策划与创作", "短视频/图文脚本撰写", "直播内容支持", "内容效果数据分析"],
     "req": ["本科及以上，专业不限", "文案功底扎实，理解短视频", "具备数据分析能力", "审美在线，有电商内容实习优先"]},
    {"company": "新媒时代", "industry": "专业服务", "category": "内容运营", "title": "内容运营编辑", "city": "北京", "education": "本科及以上", "salary": "8-12K", "certs": [],
     "resp": ["公众号内容创作与选题策划", "排版发布与账号维护", "粉丝互动与增长"],
     "req": ["本科及以上，新闻/中文专业优先", "文字功底扎实", "熟悉排版工具", "热点敏感，责任心强"]},
    # ============ 运营-电商运营 ============
    {"company": "快享", "industry": "快消", "category": "电商运营", "title": "电商运营（校招）", "city": "杭州", "education": "本科及以上", "salary": "10-16K", "certs": [],
     "resp": ["店铺日常运营与维护", "活动报名与策划执行", "运营数据日报输出", "供应链与库存协同"],
     "req": ["本科及以上，专业不限", "了解电商平台运营规则", "Excel 熟练，数据分析能力强", "抗压能力强", "有淘宝/京东实习优先"]},
    {"company": "智造云", "industry": "制造业", "category": "电商运营", "title": "跨境电商运营", "city": "深圳", "education": "本科及以上", "salary": "9-14K", "certs": [],
     "resp": ["亚马逊/独立站日常运营", "listing 优化与广告投放", "库存管理与补货计划"],
     "req": ["本科及以上，专业不限", "英语读写能力良好", "了解电商基础运营", "Excel 熟练", "了解亚马逊平台优先"]},
    {"company": "星选严选", "industry": "快消", "category": "电商运营", "title": "电商运营助理", "city": "上海", "education": "本科及以上", "salary": "9-13K", "certs": [],
     "resp": ["平台运营支持与活动执行", "数据整理与报表输出", "客服与售后协同"],
     "req": ["本科及以上，专业不限", "了解电商行业", "Excel 熟练，细心负责", "沟通能力强"]},
    # ============ 运营-新媒体运营 ============
    {"company": "新媒时代", "industry": "专业服务", "category": "新媒体运营", "title": "新媒体运营（校招）", "city": "北京", "education": "本科及以上", "salary": "8-13K", "certs": [],
     "resp": ["双微/抖音账号运营", "内容策划与发布", "粉丝增长与互动", "数据复盘与优化"],
     "req": ["本科及以上，专业不限", "网感好，文案能力强", "了解短视频基础玩法", "具备数据分析能力", "热点敏感"]},
    {"company": "快享", "industry": "快消", "category": "新媒体运营", "title": "新媒体运营（品牌向）", "city": "杭州", "education": "本科及以上", "salary": "9-14K", "certs": [],
     "resp": ["品牌内容传播策划", "达人合作执行与跟进", "内容排期与效果分析"],
     "req": ["本科及以上，专业不限", "文案能力强，审美在线", "了解小红书/抖音平台", "数据分析基础", "有品牌实习加分"]},
    {"company": "星辰互动", "industry": "互联网", "category": "新媒体运营", "title": "新媒体运营（游戏）", "city": "广州", "education": "本科及以上", "salary": "9-14K", "certs": [],
     "resp": ["游戏内容传播与话题策划", "活动素材跟进", "用户互动与舆情维护"],
     "req": ["本科及以上，专业不限", "热爱游戏，网感好", "文案能力强", "数据敏感，责任心强"]},
    # ============ 市场-市场营销 ============
    {"company": "快享", "industry": "快消", "category": "市场营销", "title": "市场管培生（校招）", "city": "杭州", "education": "本科及以上", "salary": "11-16K", "certs": [],
     "resp": ["品牌活动策划与执行", "市场调研与消费者洞察", "渠道协同与落地", "活动数据分析"],
     "req": ["本科及以上，市场营销/广告专业优先", "有活动策划执行经验", "PPT/Excel 熟练", "创新意识与沟通能力强", "有快消实习优先"]},
    {"company": "星图金融", "industry": "金融", "category": "市场营销", "title": "市场营销专员（应届）", "city": "上海", "education": "本科及以上", "salary": "10-15K", "certs": [],
     "resp": ["金融产品营销策划", "渠道活动执行与物料跟进", "营销效果复盘分析"],
     "req": ["本科及以上，市场营销相关专业", "掌握市场营销基础理论", "文案与活动策划能力强", "数据分析基础", "了解金融行业优先"]},
    {"company": "探路者咨询", "industry": "咨询", "category": "市场营销", "title": "市场分析助理", "city": "北京", "education": "本科及以上", "salary": "12-18K", "certs": [],
     "resp": ["行业研究资料收集整理", "竞品分析与市场数据收集", "研究报告撰写"],
     "req": ["本科及以上，经济/管理相关专业", "研究能力强，逻辑清晰", "Excel 熟练，Python 加分", "PPT 制作能力强", "有咨询实习优先"]},
    {"company": "智造云", "industry": "制造业", "category": "市场营销", "title": "市场专员（B2B）", "city": "深圳", "education": "本科及以上", "salary": "9-14K", "certs": [],
     "resp": ["行业展会与活动参与", "销售线索管理与跟进", "内容营销支持与竞品分析"],
     "req": ["本科及以上，市场营销相关专业", "办公软件熟练", "沟通表达能力强", "了解 B2B 业务加分", "执行力强"]},
    {"company": "元启智能", "industry": "互联网", "category": "市场营销", "title": "产品市场营销（校招）", "city": "深圳", "education": "本科及以上", "salary": "12-18K", "certs": [],
     "resp": ["产品上市营销策划", "用户洞察与市场调研", "内容与活动策划执行", "投放数据协助分析"],
     "req": ["本科及以上，市场/广告专业优先", "掌握用户画像与市场调研方法", "文案能力强", "数据分析基础", "自驱力强"]},
    # ============ 市场-品牌公关 ============
    {"company": "快享", "industry": "快消", "category": "品牌公关", "title": "品牌公关专员（校招）", "city": "杭州", "education": "本科及以上", "salary": "11-16K", "certs": [],
     "resp": ["品牌传播活动执行", "媒体关系维护", "新闻稿件撰写", "公关活动支持"],
     "req": ["本科及以上，新闻/广告专业优先", "文字功底扎实", "沟通协调能力强", "热点敏感，责任心强"]},
    {"company": "星辰互动", "industry": "互联网", "category": "品牌公关", "title": "公关专员", "city": "广州", "education": "本科及以上", "salary": "10-15K", "certs": [],
     "resp": ["公关稿件撰写与发布", "媒体合作与资源维护", "舆情监测与应对", "公关活动执行"],
     "req": ["本科及以上，新闻传播相关专业", "写作能力强", "沟通表达优秀", "责任心强，抗压"]},
    {"company": "星图金融", "industry": "金融", "category": "品牌公关", "title": "品牌公关（应届）", "city": "上海", "education": "本科及以上", "salary": "10-15K", "certs": [],
     "resp": ["品牌活动策划与执行", "新闻稿撰写与媒体对接", "舆情监测与报告"],
     "req": ["本科及以上，传播/新闻专业", "文案与表达能力优秀", "了解金融行业加分", "细心负责"]},
    # ============ 市场-市场推广 ============
    {"company": "途行", "industry": "互联网", "category": "市场推广", "title": "市场推广专员（渠道）", "city": "上海", "education": "本科及以上", "salary": "9-14K", "certs": [],
     "resp": ["渠道推广执行与跟进", "投放数据整理与分析", "素材跟进与优化", "渠道关系维护"],
     "req": ["本科及以上，专业不限", "掌握市场推广基础", "Excel 熟练，数据敏感", "沟通能力强", "结果导向"]},
    {"company": "数澜智能", "industry": "互联网", "category": "市场推广", "title": "市场推广（校招）", "city": "杭州", "education": "本科及以上", "salary": "9-14K", "certs": [],
     "resp": ["线下活动策划与执行", "内容分发与线索收集", "推广数据统计"],
     "req": ["本科及以上，专业不限", "执行力强，结果导向", "办公软件熟练", "沟通表达清晰"]},
    # ============ 职能-人力资源 ============
    {"company": "云启科技", "industry": "互联网", "category": "人力资源", "title": "HR 管培生（校招）", "city": "北京", "education": "本科及以上", "salary": "10-15K", "certs": [],
     "resp": ["招聘全流程支持", "员工关系与入职管理", "培训组织与落地", "人事数据报表"],
     "req": ["本科及以上，人力资源/管理类专业优先", "沟通能力强，细心负责", "Excel 熟练", "有人力资源实习经验优先"]},
    {"company": "星图金融", "industry": "金融", "category": "人力资源", "title": "招聘专员（应届）", "city": "上海", "education": "本科及以上", "salary": "9-14K", "certs": [],
     "resp": ["岗位发布与简历筛选", "面试安排与跟进", "Offer 流程支持"],
     "req": ["本科及以上，人力资源相关专业", "沟通与执行能力强", "有招聘实习经验优先", "细心，抗压"]},
    {"company": "快享", "industry": "快消", "category": "人力资源", "title": "HR 专员（员工关系）", "city": "杭州", "education": "本科及以上", "salary": "9-13K", "certs": [],
     "resp": ["入离职手续办理", "社保公积金操作", "员工活动组织", "人事档案管理"],
     "req": ["本科及以上，人力资源相关专业", "细心负责，沟通能力强", "Excel 熟练", "了解劳动法基础"]},
    {"company": "智造云", "industry": "制造业", "category": "人力资源", "title": "人事专员（培训方向）", "city": "深圳", "education": "本科及以上", "salary": "8-12K", "certs": [],
     "resp": ["培训计划制定与执行", "新员工培训组织", "培训档案与课程管理"],
     "req": ["本科及以上，人力资源相关专业", "表达能力与组织能力强", "PPT 制作熟练", "责任心强"]},
    # ============ 职能-财务 ============
    {"company": "星图金融", "industry": "金融", "category": "财务", "title": "财务管培生（应届）", "city": "上海", "education": "本科及以上", "salary": "10-16K", "certs": ["CPA", "ACCA"],
     "resp": ["财务核算与凭证处理", "预算管理与执行分析", "税务申报支持", "财务报表编制"],
     "req": ["本科及以上，财务/会计专业", "会计基础扎实", "Excel 熟练，财务软件了解", "CPA/ACCA 在考优先", "细心负责"]},
    {"company": "快享", "industry": "快消", "category": "财务", "title": "财务分析专员（校招）", "city": "杭州", "education": "本科及以上", "salary": "10-15K", "certs": ["CPA"],
     "resp": ["经营数据分析与报告", "预算编制与执行跟踪", "成本分析与控制"],
     "req": ["本科及以上，财会相关专业", "Excel 熟练，财务分析基础", "数据分析能力强", "CPA 加分", "逻辑清晰"]},
    {"company": "探路者咨询", "industry": "咨询", "category": "财务", "title": "财务咨询助理", "city": "北京", "education": "硕士及以上", "salary": "14-20K", "certs": ["CPA", "ACCA"],
     "resp": ["财务尽调数据支持", "财务数据处理与建模", "咨询报告撰写", "客户沟通"],
     "req": ["硕士及以上，财会/金融专业", "Excel 熟练，PPT 能力强", "财务分析基础扎实", "CPA/ACCA 加分", "抗压能力强"]},
    {"company": "云启科技", "industry": "互联网", "category": "财务", "title": "会计（应收方向）", "city": "北京", "education": "本科及以上", "salary": "9-13K", "certs": ["初级会计"],
     "resp": ["应收账款核算与对账", "发票开具与管理", "凭证整理与归档"],
     "req": ["本科及以上，会计专业", "会计基础扎实", "Excel 熟练", "细心，初级会计证优先"]},
    # ============ 职能-法务 ============
    {"company": "云启科技", "industry": "互联网", "category": "法务", "title": "法务专员（校招）", "city": "北京", "education": "硕士及以上", "salary": "15-22K", "certs": ["法律职业资格"],
     "resp": ["合同审核与模板建设", "合规审查与支持", "知识产权事务", "纠纷处理协助"],
     "req": ["硕士及以上，法学专业", "通过法律职业资格考试优先", "合同审查基础扎实", "沟通严谨，责任心强"]},
    {"company": "快享", "industry": "快消", "category": "法务", "title": "法务助理", "city": "杭州", "education": "本科及以上", "salary": "10-15K", "certs": ["法律职业资格"],
     "resp": ["合同流程管理与归档", "法务文档整理", "合规检查协助"],
     "req": ["本科及以上，法学专业", "通过或备考法律职业资格考试", "文档处理细心", "沟通能力强"]},
    # ============ 职能-行政 ============
    {"company": "智造云", "industry": "制造业", "category": "行政", "title": "行政专员（校招）", "city": "深圳", "education": "本科及以上", "salary": "7-10K", "certs": [],
     "resp": ["行政接待与办公环境管理", "固定资产与物资管理", "员工活动组织"],
     "req": ["本科及以上，专业不限", "沟通与组织能力强", "办公软件熟练", "细心负责"]},
    # ============ 求稳赛道：银行（M7.13，考试制网申+笔试） ============
    {"company": "长沙银行", "industry": "金融", "category": "综合柜员", "title": "综合柜员（校招）", "city": "长沙", "education": "本科及以上", "salary": "8-12K",
     "certs": ["银行从业资格"], "stability": "bank", "selection": "exam",
     "exam_note": "银行校招流程：网申→笔试（行测+经济金融）→面试→体检；每年秋招 9-10 月开启",
     "tags": ["银行", "柜员", "求稳"],
     "resp": ["现金存取款、转账、挂失等柜面业务办理", "厅堂客户引导与基础营销", "反洗钱与合规操作要求执行", "班后账务核对与凭证整理"],
     "req": ["本科及以上，金融/经济/会计/管理类专业优先", "形象端正，普通话标准", "细心严谨，服务意识强", "熟练五笔/小键盘、办公软件", "需通过银行从业资格考试"],
    },
    {"company": "某国有大行长沙分行", "industry": "金融", "category": "综合柜员", "title": "综合柜员（定向招聘）", "city": "长沙", "education": "本科及以上", "salary": "7-11K",
     "certs": ["银行从业资格"], "stability": "bank", "selection": "exam",
     "exam_note": "国有行校招统一网申：笔试考察行测、英语与金融基础知识，通过后分行面试",
     "tags": ["银行", "国有行", "柜员", "求稳"],
     "resp": ["个人/对公柜面业务办理与合规操作", "大堂客户分流与产品转介", "反洗钱与账户管理要求执行"],
     "req": ["本科及以上，专业不限（财经类优先）", "无不良记录，政审合格", "服务意识与抗压能力", "通过银行从业资格者优先"],
    },
    {"company": "招商银行", "industry": "金融", "category": "客户经理助理", "title": "零售客户经理助理（校招）", "city": "深圳", "education": "本科及以上", "salary": "10-15K",
     "certs": [], "stability": "bank", "selection": "exam",
     "exam_note": "股份制银行校招：网申→统一笔试→多轮面试；业绩导向岗位晋升较快",
     "tags": ["银行", "客户经理", "零售", "求稳"],
     "resp": ["协助客户经理维护零售客户关系", "信用卡/理财产品的基础营销", "客户档案整理与系统录入", "厅堂客户接待与需求挖掘"],
     "req": ["本科及以上，金融/市场营销/管理专业优先", "沟通表达与抗压能力强", "对销售工作有热情", "熟练办公软件与 CRM 系统"],
    },
    {"company": "广发银行", "industry": "金融", "category": "客户经理助理", "title": "对公客户经理助理", "city": "广州", "education": "本科及以上", "salary": "9-13K",
     "certs": ["基金从业资格"], "stability": "bank", "selection": "exam",
     "tags": ["银行", "对公", "客户经理", "求稳"],
     "resp": ["协助对公客户经理维护企业客户", "开户尽调资料整理与归档", "对公产品（结算/授信）基础营销", "行业与企业信息收集"],
     "req": ["本科及以上，金融/会计/经济专业", "数据分析与公文写作能力", "责任心强，可出差", "基金从业资格或备考中"],
    },
    {"company": "兴业银行", "industry": "金融", "category": "运营支持", "title": "运营支持岗（集中作业）", "city": "福州", "education": "本科及以上", "salary": "7-10K",
     "certs": [], "stability": "bank", "selection": "exam",
     "tags": ["银行", "运营", "后台", "求稳"],
     "resp": ["远程集中授权与凭证扫描复核", "对账与差错处理", "业务流程优化数据统计"],
     "req": ["本科及以上，专业不限", "细心、准确率高", "能适应轮班", "办公软件熟练"],
    },
    {"company": "邮储银行", "industry": "金融", "category": "综合柜员", "title": "柜员/大堂经理（县域定向）", "city": "成都", "education": "大专及以上", "salary": "6-9K",
     "certs": [], "stability": "bank", "selection": "exam",
     "exam_note": "县域定向岗位竞争较小、稳定性高，服务期满后可在县域内调动",
     "tags": ["银行", "县域", "柜员", "求稳"],
     "resp": ["柜面业务办理与厅堂服务", "金融普惠业务宣传", "反洗钱合规操作"],
     "req": ["大专及以上，本地生源优先", "吃苦耐劳，能扎根县域", "普通话标准，服务意识强"],
    },
    {"company": "宁波银行", "industry": "金融", "category": "管理培训生", "title": "分行管理培训生（校招）", "city": "宁波", "education": "硕士及以上", "salary": "12-18K",
     "certs": [], "stability": "bank", "selection": "exam",
     "exam_note": "管培生需经历柜面/营销/中台多岗位轮岗 1-2 年，培养方向为分支行管理者",
     "tags": ["银行", "管培生", "轮岗", "求稳"],
     "resp": ["多岗位轮岗学习（柜面/零售/对公/中后台）", "参与专项业务项目", "撰写经营分析与调研报告"],
     "req": ["硕士及以上，金融/经济/管理/数学专业", "成绩排名前 30%", "组织协调与文字能力强", "有学生干部/实习经历优先"],
    },
    {"company": "某城商行", "industry": "金融", "category": "运营支持", "title": "风险管理助理（校招）", "city": "杭州", "education": "本科及以上", "salary": "9-13K",
     "certs": [], "stability": "bank", "selection": "mixed",
     "tags": ["银行", "风控", "中台", "求稳"],
     "resp": ["信贷材料初审与风险点标注", "贷后预警数据整理", "监管报表数据填报", "反欺诈规则维护协助"],
     "req": ["本科及以上，金融/统计/法律专业", "数据分析基础扎实", "严谨细致，原则性强", "Excel/SQL 熟练优先"],
    },
    # ============ 求稳赛道：央国企（M7.13） ============
    {"company": "国家电网湖南分公司", "industry": "专业服务", "category": "行政", "title": "综合行政岗（校招）", "city": "长沙", "education": "本科及以上", "salary": "8-12K",
     "certs": [], "stability": "soe", "selection": "exam",
     "exam_note": "央国企校招：网申→统一笔试（行测+企业文化）→结构化面试；国家电网一批约 12 月笔试",
     "tags": ["央国企", "国家电网", "行政", "求稳"],
     "resp": ["公文写作与会议组织", "党建宣传材料整理", "档案与固定资产管理", "员工活动组织"],
     "req": ["本科及以上，中文/行政管理/公共管理专业", "中共党员优先", "文字功底扎实", "熟练办公软件"],
    },
    {"company": "中国移动湖南分公司", "industry": "互联网", "category": "用户运营", "title": "客户服务运营岗（校招）", "city": "长沙", "education": "本科及以上", "salary": "8-12K",
     "certs": [], "stability": "soe", "selection": "exam",
     "tags": ["央国企", "运营商", "运营", "求稳"],
     "resp": ["客户满意度数据分析", "服务流程优化提案", "投诉工单分析与回访", "服务指标报表制作"],
     "req": ["本科及以上，统计/管理/通信类专业", "数据分析与 PPT 汇报能力强", "沟通耐心，服务意识强"],
    },
    {"company": "中国建筑某局", "industry": "制造业", "category": "财务", "title": "财务岗（校招）", "city": "武汉", "education": "本科及以上", "salary": "8-11K",
     "certs": ["初级会计"], "stability": "soe", "selection": "direct",
     "exam_note": "部分央企对财务等通用岗直接简历筛选+面试，不设统一笔试",
     "tags": ["央国企", "建筑", "财务", "求稳"],
     "resp": ["项目费用报销与核算", "资金计划编制", "税务申报协助", "项目财务台账管理"],
     "req": ["本科及以上，会计/财务管理专业", "能接受驻项目", "初级会计证", "责任心强"],
    },
    {"company": "中石化销售公司", "industry": "制造业", "category": "市场营销", "title": "营销管理岗（校招）", "city": "广州", "education": "本科及以上", "salary": "8-12K",
     "certs": [], "stability": "soe", "selection": "exam",
     "tags": ["央国企", "石化", "营销", "求稳"],
     "resp": ["加油站零售数据分析", "营销活动方案执行", "渠道客户维护", "市场信息收集与竞品分析"],
     "req": ["本科及以上，市场营销/工商管理/油气储运专业", "数据敏感度高", "能出差，性格外向"],
    },
    {"company": "某省属国企集团", "industry": "金融", "category": "管理培训生", "title": "集团管培生（校招）", "city": "合肥", "education": "硕士及以上", "salary": "10-15K",
     "certs": [], "stability": "soe", "selection": "exam",
     "tags": ["央国企", "管培生", "集团", "求稳"],
     "resp": ["集团总部与子公司轮岗", "参与战略与投资研究", "撰写经营分析报告", "对接政府与监管事项"],
     "req": ["硕士及以上，经济/金融/会计专业", "文字与调研能力强", "中共党员优先", "接受轮岗安排"],
    },
    {"company": "中国邮政储蓄", "industry": "金融", "category": "综合柜员", "title": "代理金融网点柜员（县聘）", "city": "南昌", "education": "大专及以上", "salary": "5-8K",
     "certs": [], "stability": "soe", "selection": "exam",
     "tags": ["央国企", "邮政", "县聘", "求稳"],
     "resp": ["邮政储蓄柜面业务办理", "汇兑与代收付业务", "网点营销与客户维护"],
     "req": ["大专及以上，本地优先", "服务意识强，能吃苦", "合规意识强"],
    },
]


async def seed_all(session: AsyncSession, force: bool = False) -> dict:
    """幂等灌入分类树/技能本体/证书/工具链/岗位库。返回各表计数。

    守卫条件：分类树、技能本体、岗位库三者齐备才跳过——若仅岗位库有数据
    （如先经 CLI 爬虫灌入）而分类/本体缺失，仍会补种分类与本体。
    """
    jd_count = await session.scalar(select(func.count()).select_from(JdLibrary)) or 0
    cat_count = await session.scalar(select(func.count()).select_from(JdCategory)) or 0
    ont_count = await session.scalar(select(func.count()).select_from(JdSkillOntology)) or 0
    if jd_count > 0 and cat_count > 0 and ont_count > 0 and not force:
        return {"skipped": True, "jd_count": jd_count}

    if force:
        # 重灌：先清空依赖表（子表先行）；岗位库仅清空人工种子，
        # 保留用户投稿/爬虫数据（source='crawler'/'user_submit'/'api'）
        for model in (Recommendation, ToolchainTemplate):
            await session.execute(delete(model))
        await session.execute(delete(JdLibrary).where(JdLibrary.source == "manual"))
        for model in (CertScarcity, JdSkillOntology, JdCategory):
            await session.execute(delete(model))

    # 1. 行业节点
    industry_ids: dict[str, uuid_str] = {}
    for name in INDUSTRIES:
        node = JdCategory(dim="industry", name=name, level=1)
        session.add(node)
        await session.flush()
        industry_ids[name] = node.id

    # 2. 职能树（一级职能 + 二级细分叶子）
    function_ids: dict[str, uuid_str] = {}
    leaf_ids: dict[str, uuid_str] = {}
    for func_name, leaves in FUNCTION_TREE.items():
        fn = JdCategory(dim="function", name=func_name, level=1)
        session.add(fn)
        await session.flush()
        function_ids[func_name] = fn.id
        for leaf in leaves:
            node = JdCategory(dim="function", parent_id=fn.id, name=leaf, level=2)
            session.add(node)
            await session.flush()
            leaf_ids[leaf] = node.id

    # 3. 技能本体
    for canonical, aliases, skill_class, is_core in SKILL_ONTOLOGY:
        session.add(
            JdSkillOntology(
                canonical_name=canonical, aliases=aliases, skill_class=skill_class,
                is_core_default=is_core,
            )
        )

    # 4. 证书稀缺度
    for name, aliases, score, hint in CERT_SCARCITY:
        session.add(
            CertScarcity(cert_name=name, aliases=aliases, scarcity_score=score, level_hint=hint)
        )

    # 5. 工具链模板
    for cat, toolchain in TOOLCHAIN_TEMPLATES.items():
        cid = leaf_ids.get(cat)
        if cid:
            session.add(ToolchainTemplate(category_id=cid, toolchain=toolchain))

    await session.flush()

    # 6. 岗位库（jd_parsed 用本体扫描回填技能/证书）
    ontology = await load_ontology(session)
    add_words(ontology.skill_terms)
    now = datetime.now(timezone.utc)
    for seed in JD_SEEDS:
        cat_id = leaf_ids.get(seed["category"])
        ind_id = industry_ids.get(seed["industry"])
        resp = seed["resp"]
        req = seed["req"]
        jd_text = (
            f"【{seed['title']}】\n\n岗位职责：\n"
            + "\n".join(f"- {r}" for r in resp)
            + "\n\n任职要求：\n"
            + "\n".join(f"- {r}" for r in req)
        )
        skills = sorted(scan_skills(jd_text, ontology))
        certs = seed.get("certs") or sorted(scan_certs(jd_text, ontology))
        jd_parsed: dict = {"skills": skills, "certs": certs, "hard": {"education": seed["education"]}}
        _attach_stability_meta(jd_parsed, seed)
        session.add(
            JdLibrary(
                source="manual",
                company=seed["company"],
                industry_id=ind_id,
                category_id=cat_id,
                title=seed["title"],
                city=seed["city"],
                education=seed["education"],
                salary_range=seed["salary"],
                jd_text=jd_text,
                jd_parsed=jd_parsed,
                quality_score=1.0,
                is_active=True,
                crawl_at=now,
            )
        )
    await session.commit()

    counts = {
        "skipped": False,
        "industries": len(INDUSTRIES),
        "functions": len(FUNCTION_TREE),
        "leaves": sum(len(v) for v in FUNCTION_TREE.values()),
        "skills": len(SKILL_ONTOLOGY),
        "certs": len(CERT_SCARCITY),
        "jd_count": len(JD_SEEDS),
    }
    logger.info("jd library seeded: %s", counts)
    return counts


async def ensure_seeded(session: AsyncSession) -> dict:
    """接口懒加载：分类树/本体/岗位库任一缺失时自动补种（守卫逻辑见 seed_all）；
    求稳赛道（银行/央国企）分类与岗位做幂等增量补充，老库无需 force 也可补种。"""
    result = await seed_all(session)
    if result.get("skipped"):
        result = await ensure_stability_seed(session)
    return result


def _attach_stability_meta(jd_parsed: dict, seed: dict) -> None:
    """求稳赛道种子 → jd_parsed.meta（stability/selection/exam_note/tags），
    供推荐/列表/详情展示与筛选（不改表结构，随自由 JSON 存储）。"""
    meta: dict = {}
    for key in ("stability", "selection", "exam_note", "tags"):
        if seed.get(key):
            meta[key] = seed[key]
    if meta:
        jd_parsed["meta"] = meta


async def ensure_stability_seed(session: AsyncSession) -> dict:
    """幂等增量补种：求稳赛道（金融综合职能树 + 银行/央国企岗位）。

    老库（已有分类树/岗位）升级时无需 force 重灌——本函数只补缺的分类叶子与
    缺失的求稳岗位（按 title+company 去重），不影响既有用户/爬虫数据。
    """
    from ...models import JdCategory as _Cat

    # 1) 确保「金融综合」一级 + 二级叶子存在
    leaf_ids: dict[str, Any] = {}
    for func_name, leaves in FUNCTION_TREE.items():
        if func_name != "金融综合":
            continue
        fn = await session.scalar(
            select(_Cat).where(_Cat.dim == "function", _Cat.name == func_name, _Cat.level == 1)
        )
        if fn is None:
            fn = _Cat(dim="function", name=func_name, level=1)
            session.add(fn)
            await session.flush()
        for leaf in leaves:
            node = await session.scalar(
                select(_Cat).where(_Cat.dim == "function", _Cat.name == leaf, _Cat.parent_id == fn.id)
            )
            if node is None:
                node = _Cat(dim="function", parent_id=fn.id, name=leaf, level=2)
                session.add(node)
                await session.flush()
            leaf_ids[leaf] = node.id

    stability_seeds = [s for s in JD_SEEDS if s.get("stability")]
    if not stability_seeds:
        await session.commit()
        return {"added": 0, "skipped": 0}

    # 2) 行业名 → id（应为既有行业；缺失则跳过该条）
    ind_rows = (await session.execute(select(JdCategory).where(JdCategory.dim == "industry"))).scalars().all()
    industry_ids = {r.name: r.id for r in ind_rows}

    # 3) 缺失的求稳岗位（按 title+company 去重）
    existing = {
        (r[0], r[1])
        for r in (
            await session.execute(
                select(JdLibrary.title, JdLibrary.company).where(JdLibrary.source == "manual")
            )
        ).all()
    }
    ontology = await load_ontology(session)
    now = datetime.now(timezone.utc)
    added = skipped = 0
    for seed in stability_seeds:
        if (seed["title"], seed["company"]) in existing:
            skipped += 1
            continue
        cat_id = leaf_ids.get(seed["category"]) or leaf_ids.get("运营支持")
        ind_id = industry_ids.get(seed["industry"])
        jd_text = (
            f"【{seed['title']}】\n\n岗位职责：\n"
            + "\n".join(f"- {r}" for r in seed["resp"])
            + "\n\n任职要求：\n"
            + "\n".join(f"- {r}" for r in seed["req"])
        )
        skills = sorted(scan_skills(jd_text, ontology))
        certs = seed.get("certs") or sorted(scan_certs(jd_text, ontology))
        jd_parsed: dict = {"skills": skills, "certs": certs, "hard": {"education": seed["education"]}}
        _attach_stability_meta(jd_parsed, seed)
        session.add(
            JdLibrary(
                source="manual",
                company=seed["company"],
                industry_id=ind_id,
                category_id=cat_id,
                title=seed["title"],
                city=seed["city"],
                education=seed["education"],
                salary_range=seed["salary"],
                jd_text=jd_text,
                jd_parsed=jd_parsed,
                quality_score=1.0,
                is_active=True,
                crawl_at=now,
            )
        )
        added += 1
    await session.commit()
    logger.info("stability seed ensured: added=%d skipped=%d", added, skipped)
    return {"added": added, "skipped": skipped}


async def _main() -> None:
    import sys

    force = len(sys.argv) > 1 and sys.argv[1] == "force"
    async with SessionLocal() as session:
        result = await seed_all(session, force=force)
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
