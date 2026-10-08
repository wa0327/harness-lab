請在目前的工作目錄寫一個多旋翼無人機的 GNC（導引、導航、控制）程式 gnc.py。機上相機看到目標後，要全速接近並撞上目標。程式根據相機給的目標框、相機內參與安裝角，結合飛控回報的姿態、位置與速度，每拍對飛控下達速度命令。

工作目錄裡的 sim.py 是模擬器，會把 gnc.py 當子程序執行。協定、座標慣例、撞擊判定與全部情境都寫在 sim.py 裡，請先讀它。

- `python3 sim.py` 跑全部情境、`python3 sim.py <情境名>` 跑單一情境，加 `--trace <目錄>` 會存下每拍的紀錄。
- `python3 -m unittest -q` 是評分用的測試，每個情境一個。

可以從這個骨幹開始，填寫 `Gnc` 的內容：

```python
import json
import sys


class Gnc:
    def __init__(self, camera, fc, dt):
        """camera：相機內參與安裝角；fc：飛控參數；dt：每拍間隔 [s]。"""
        self.camera = camera
        self.fc = fc
        self.dt = dt

    def update(self, t, det, att, pos_ned, vel_ned):
        """每拍呼叫一次，回傳這一拍的速度命令。

        t：時間 [s]；det：目標框（畫幅歸一化的 cx、cy、w、h）或 None；
        att：姿態 roll、pitch、yaw、pitchspeed [rad, rad/s]；
        pos_ned、vel_ned：飛控回報的位置 [m] 與速度 [m/s]（NED）。
        """
        return {"v_fwd": 0.0, "v_right": 0.0, "v_up": 0.0, "yaw_rate": 0.0}


def main():
    gnc = None
    for line in sys.stdin:
        msg = json.loads(line)
        if msg["type"] == "init":
            gnc = Gnc(msg["camera"], msg["fc"], msg["dt"])
        elif msg["type"] == "tick":
            cmd = gnc.update(msg["t"], msg["det"], msg["att"], msg["pos_ned"], msg["vel_ned"])
            sys.stdout.write(json.dumps(cmd) + "\n")
            sys.stdout.flush()
        elif msg["type"] == "end":
            break


if __name__ == "__main__":
    main()
```

限制：

- 不可以修改 sim.py 和 test_gnc.py。評分一律用原檔，改了只會騙到自己，而且會被判不及格。
- 只能用 Python 標準函式庫（評分用的 python3 沒有 numpy）。gnc.py 可以 import 工作目錄裡你自己寫的其他模組。
- GNC 只能使用協定送來的資訊。不可以讀取模擬器的內部狀態，也不可以依情境名稱或已知的目標軌跡寫死行為。
- 只讀目前工作目錄裡的檔案。

持續改進，直到全部測試通過，或你判斷已無法再改進為止。最後在工作目錄寫 README.md，說明整體架構、導引與控制的設計決策、各情境的結果，以及沒通過的情境的原因分析。
