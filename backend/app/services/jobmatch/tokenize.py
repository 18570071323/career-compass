"""轻量中文分词：优先 jieba（若已安装），否则回退「拉丁词 + CJK 字符二元组」。

TF-IDF 只需词条切分即可，二元组方案对中文检索效果足够；技能词条另由
匹配层按技能本体扫描注入，不依赖分词质量。
"""
from __future__ import annotations

import re

try:  # jieba 为可选依赖（M7.1 起引入）
    import jieba  # type: ignore

    _HAS_JIEBA = True
except Exception:  # noqa: BLE001
    _HAS_JIEBA = False

_LATIN_RE = re.compile(r"[a-zA-Z0-9+#.\-]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_NON_WORD = "a-z0-9+#"

# 通用停用词（岗位文本高频虚词/泛词；技能词不在其中）
_STOPWORDS = {
    "的", "了", "和", "与", "及", "在", "为", "等", "或", "对", "从", "到", "于", "并", "及",
    "岗位", "职责", "要求", "任职", "负责", "参与", "熟悉", "了解", "具备", "优先", "以上",
    "相关", "工作", "经验", "能力", "良好", "积极", "团队", "沟通", "协作", "能够", "可以",
    "具有", "进行", "包括", "以及", "根据", "通过", "配合", "协助", "跟进", "完成", "使用",
    "日常", "业务", "相关方", "我们", "你将", "机会", "加入",
}

_ADDED_WORDS: set[str] = set()


def add_words(words: list[str]) -> None:
    """向 jieba 词典注入领域词（技能本体等），幂等。"""
    if not _HAS_JIEBA:
        return
    for w in words:
        w = (w or "").strip().lower()
        if w and w not in _ADDED_WORDS:
            jieba.add_word(w)
            _ADDED_WORDS.add(w)


def tokenize(text: str) -> list[str]:
    """分词并过滤：返回小写词条列表（长度≥2 的非纯数字）。"""
    text = (text or "").lower()
    tokens: list[str] = []
    if _HAS_JIEBA:
        for t in jieba.lcut(text):
            t = t.strip()
            if not t:
                continue
            if _CJK_RE.search(t):
                if len(t) >= 2:
                    tokens.append(t)
            else:
                tokens.append(t.lower())
    else:
        for m in _LATIN_RE.finditer(text):
            tokens.append(m.group(0).lower())
        cjk = _CJK_RE.findall(text)
        tokens.extend("".join(cjk[i : i + 2]) for i in range(len(cjk) - 1))
    return [t for t in tokens if t not in _STOPWORDS and not t.isdigit()]


def _term_in(text: str, term: str) -> bool:
    """词条匹配：纯拉丁词（如 C/BI/SQL/C++）用词边界，避免 'ml' 误命中 'html'、
    'go' 误命中 'google'、'c' 命中任意拉丁文本；中文词条按子串（'数据'命中'数据库'）。"""
    if term and term.isascii() and all(ch.isalnum() or ch in "+#" for ch in term):
        return re.search(rf"(?<![{_NON_WORD}]){re.escape(term)}(?![{_NON_WORD}])", text) is not None
    return term in text


def tokenize_with_skills(text: str, skill_terms: list[str]) -> list[str]:
    """分词 + 注入技能词条（技能词按本体扫描，不依赖分词）。"""
    add_words(skill_terms)
    toks = tokenize(text)
    lower = text.lower()
    # 词边界匹配注入：与匹配层 _term_in 语义一致，防短词/重叠词（ml⊂html、go⊂google）污染向量
    extra = [s for s in skill_terms if s and _term_in(lower, s)]
    return toks + extra
