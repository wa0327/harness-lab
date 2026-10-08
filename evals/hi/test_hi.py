"""冒煙測試：harness、模型伺服器、模型整條路都通，最終回覆裡就會有 hi。

final.md 是 agent-test.sh 在 harness 結束後寫進 run 目錄的最終回覆，在跑測試之前就已經產生。
"""

import pathlib
import unittest


class TestHi(unittest.TestCase):
    def test_reply_says_hi(self):
        reply = (pathlib.Path(__file__).parent / "final.md").read_text(encoding="utf-8")
        self.assertIn("hi", reply.lower())


if __name__ == "__main__":
    unittest.main()
