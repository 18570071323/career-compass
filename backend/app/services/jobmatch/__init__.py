"""C 端应届生求职：岗位库推荐（docs/07，M7.1）。

- parse.py    应届生简历结构化解析（DeepSeek JSON）
- tokenize.py 轻量中文分词（jieba 可选，回退字符二元组）
- matching.py TF-IDF 粗筛 + 结构化精排（本地零 LLM 成本）
- seed.py     分类树/技能本体/证书/工具链/种子岗位库
"""
