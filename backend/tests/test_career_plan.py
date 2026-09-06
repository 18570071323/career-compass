# -*- coding: utf-8 -*-
"""求职导航引擎确定性分支回归（不触网、不依赖 DB）。

覆盖：考研（保研判断/跨考/排名缺失）、考公（入党/报考窗口/每周投入）、
启动建议文案、画像不输出未采集字段。运行：cd apps/api && python -m unittest discover -s tests
"""
import asyncio
import os
import sys
import unittest

# 沙箱可能以 safe-path 运行（sys.path 不含 cwd/PYTHONPATH），显式加入 apps/api 根
_API_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)

from app.services.jobmatch import career_plan as cp  # noqa: E402


def _plan(q: dict) -> dict:
    return asyncio.run(cp.compute_career_plan(None, q, llm=None))


class TestGradBranch(unittest.TestCase):
    def test_top10_rank_advises_baoyan(self):
        res = _plan({
            "target_kind": "grad", "grad_scope": "same", "grad_exam": "12m",
            "grad_rank": "top10", "semesters_left": 3, "weekly_hours": 5, "major": "计算机",
        })
        keys = [x["k"] for x in res["profile"]]
        self.assertIn("专业排名", keys)
        self.assertNotIn("特质/偏好", keys)  # UI 未采集，不应编造
        titles = [a["title"] for p in res["roadmap"] for a in p["actions"]]
        self.assertTrue(any("优先冲保研" in t for t in titles))
        self.assertTrue(any("什么时候开始？因人而异" in t for t in titles))
        dims = [g["dim"] for g in res["gaps"]]
        self.assertNotIn("成绩口径", dims)  # 排名已知不提示口径

    def test_unknown_rank_no_gpa_nudges_investigate(self):
        res = _plan({
            "target_kind": "grad", "grad_scope": "cross", "grad_exam": "24m",
            "grad_rank": "unknown", "semesters_left": 5, "weekly_hours": 15,
        })
        dims = [g["dim"] for g in res["gaps"]]
        self.assertIn("成绩口径", dims)
        self.assertIn("跨考基础", dims)
        titles = [a["title"] for p in res["roadmap"] for a in p["actions"]]
        self.assertTrue(any("不建议押宝保研" in t for t in titles))


class TestCivilBranch(unittest.TestCase):
    def test_non_member_gets_party_advice(self):
        res = _plan({
            "target_kind": "civil", "civil_type": "national", "civil_exam": "gradyear",
            "party": "none", "semesters_left": 4, "weekly_hours": 10, "major": "法学",
        })
        pv = next(x["v"] for x in res["profile"] if x["k"] == "政治面貌")
        self.assertEqual(pv, "群众/其他")
        dims = [g["dim"] for g in res["gaps"]]
        self.assertIn("入党/报考条件", dims)
        titles = [a["title"] for p in res["roadmap"] for a in p["actions"]]
        self.assertTrue(any("递交入党申请" in t for t in titles))

    def test_member_no_party_gap_and_pace_uses_weekly(self):
        res = _plan({
            "target_kind": "civil", "civil_type": "province", "civil_exam": "after",
            "party": "member", "semesters_left": 6, "weekly_hours": 20,
        })
        dims = [g["dim"] for g in res["gaps"]]
        self.assertNotIn("入党/报考条件", dims)
        self.assertNotIn("入党推进", dims)
        notes = " ".join(a.get("detail", "") for p in res["roadmap"] for a in p["actions"])
        self.assertIn("毕业后一年再考", notes)
        self.assertIn("20 小时", notes)
        self.assertIn("6 个月", notes)


class TestHelpers(unittest.TestCase):
    def test_start_advice_no_standard(self):
        self.assertIn("因人而异", cp._start_advice(None, 5))
        self.assertIn("偏紧", cp._start_advice(12, 5))

    def test_civil_pace_thresholds(self):
        self.assertIn("10 个月", cp._civil_pace("gradyear", 2))
        self.assertIn("6 个月", cp._civil_pace("after", 20))

    def test_baoyan_advice_tiers(self):
        t, _ = cp._baoyan_advice("top10")
        self.assertIn("优先冲保研", t)
        t, _ = cp._baoyan_advice("low")
        self.assertIn("不建议押宝保研", t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
