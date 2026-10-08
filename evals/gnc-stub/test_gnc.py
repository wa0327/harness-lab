"""每個情境一個測試：gnc.py 在 sim.py 的情境裡撞上目標才算通過。"""
import unittest

import sim


class TestIntercept(unittest.TestCase):
    pass


def _make(case):
    def test(self):
        r = sim.run_case(case)
        self.assertTrue(r["passed"], f"{case.name}：{r['reason']}，最近距離 {r['cpa']} m")
    return test


for _c in sim.CASES:
    setattr(TestIntercept, f"test_{_c.name}", _make(_c))
