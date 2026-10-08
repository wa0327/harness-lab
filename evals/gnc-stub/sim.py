"""多旋翼視覺運動學模擬台：載具、相機、目標與接觸判定。

飛行控制規劃程式（預設是同目錄的 gnc.py）以子程序執行，經 stdin/stdout 每拍交換一行 JSON：

  模擬台 → 飛行控制規劃  開場一則 {"type": "init", "dt": 秒, "camera": {...}, "fc": {...}}
                之後每拍 {"type": "tick", "t": 秒, "det": 框或 null, "att": {...},
                         "pos_ned": [n, e, d], "vel_ned": [vn, ve, vd]}
                結束時 {"type": "end"}
  飛行控制規劃 → 模擬台  每則 tick 回一行 {"v_fwd": m/s, "v_right": m/s, "v_up": m/s, "yaw_rate": rad/s}

座標與單位：
  · 世界系 NED（北、東、下），原點在地面；pos_ned[2] = -高度。
  · att 是飛控的姿態（MAVLink ATTITUDE 慣例，弧度）：roll 右傾為正、pitch 機頭上仰為正、
    yaw 自北順時針為正；pitchspeed 是 pitch 的變化率 [rad/s]。
  · 速度命令在「水平機體系」：v_fwd 沿機頭的水平方向、v_right 向右、v_up 向上；
    yaw_rate 由上往下看順時針為正。飛控以內部速度環追這個命令（有滯後、有上限）。
  · det 是相機這一幀的目標框，對畫幅歸一化：{"cx", "cy", "w", "h"}，cx 往右增、cy 往下增，
    0~1；目標中心不在視野內時為 null。框是目標外形投影的包絡，超出畫面的部分被裁掉。
  · camera：{"res": [寬, 高], "fx", "fy", "cx", "cy"}（像素）與 "mount_pitch_deg"
    （相機相對機身的俯仰安裝角，正值 = 光軸上仰）。
  · fc：飛控參數，{"angle_max_deg", "v_up_max", "v_dn_max", "acc_z_max", "yaw_rate_max_deg"}。

情境：載具從離地 10 m、靜止、機頭朝北開始，目標在前方，依各情境的方式移動。
載具中心碰到目標外形即為接觸；90 秒內接觸且至少偵測到一次目標 = 通過。
載具距離變化率不到 1 m/s、是目標自己接觸來的接觸不算。
載具高度低於地面 = 墜地，該情境失敗。

用法：python3 sim.py [情境名 ...] [--gnc gnc.py] [--trace 目錄]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import select
import subprocess
import sys
import time
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
G = 9.80665
DT = 1 / 30
DURATION = 90.0
WALL_LIMIT = 30.0   # 每個情境的實際執行時間上限 [s]：飛行控制規劃太慢時，一次驗收不至於跑上好幾個小時
WORK_ALT = 10.0

# ── 飛控參數（交給飛行控制規劃）與載具響應（只在模擬台內）──────────────────────────
ANGLE_MAX_DEG = 35.0
A_H_MAX = G * math.tan(math.radians(ANGLE_MAX_DEG))   # 水平推力加速度上限
A_V_MAX = 5.0
V_UP_MAX = 5.0
V_DN_MAX = 3.5
YAW_RATE_MAX = math.radians(60.0)
TAU_VXY = 0.798   # 水平速度環一階時間常數 [s]
TAU_VUP = 0.394   # 上升
TAU_VDN = 0.374   # 下降
TAU_R = 0.18      # 偏航角速度環
# 穩態阻力：(水平速度 m/s, 等速平飛所需前傾角 °)
DRAG_POLAR = ((0.0, -0.35), (2.83, 6.52), (4.98, 9.38), (6.96, 10.83), (10.5, 11.98),
              (17.57, 14.45), (24.65, 19.97), (29.64, 26.3), (35.05, 35.02))

# ── 相機 ─────────────────────────────────────────────────────────────────
RES_W, RES_H = 1920, 1080
FX = FY = 1200.0
CX, CY = RES_W / 2, RES_H / 2
MOUNT_PITCH = math.radians(15.0)
CAM_OFFSET_FLU = (0.1461, 0.0, 0.058)   # 光學中心相對機身原點（前、左、上）[m]
HFOV_HALF = math.atan(CX / FX)
VFOV_HALF = math.atan(CY / FY)

# ── 目標 ─────────────────────────────────────────────────────────────────
TARGET_HALF = (4.84542 / 2, 2.03747 / 2, 1.42261 / 2)   # 半長（前後、左右、上下）[m]
TARGET_LEVER = 1.3148   # 不打滑轉向的力臂：側向速度 vl 對應偏航率 -vl/力臂

INIT = {
    "type": "init", "dt": DT,
    "camera": {"res": [RES_W, RES_H], "fx": FX, "fy": FY, "cx": CX, "cy": CY,
               "mount_pitch_deg": math.degrees(MOUNT_PITCH)},
    "fc": {"angle_max_deg": ANGLE_MAX_DEG, "v_up_max": V_UP_MAX, "v_dn_max": V_DN_MAX,
           "acc_z_max": A_V_MAX, "yaw_rate_max_deg": math.degrees(YAW_RATE_MAX)},
}


@dataclass(frozen=True)
class Case:
    name: str
    pos: tuple        # 目標起點：（前 m, 左 m, 中心離地高 m），相對載體起點與機頭
    vel: tuple = (0.0, 0.0, 0.0)   # 目標體軸速度（前、左、上）[m/s]；左向速度同時造成轉向
    heading: float = 0.0           # 目標起始航向相對載體機頭 [°]，正 = 向左
    min_agl: float = 0.0           # 目標中心最低離地高 [m]：下降到這裡就拉平


_T = (60.0, 0.0, WORK_ALT)
CASES = [
    Case("static", _T),
    Case("flee_slow", _T, (2, 0, 0)),
    Case("flee_fast", _T, (5, 0, 0)),
    Case("head_on", _T, (3, 0, 0), heading=180),
    Case("cross", _T, (5, 0, 0), heading=90),
    Case("cross_descend", _T, (5, 0, -2), heading=90),
    Case("flee_cross_descend", _T, (7.07, 0, -2), heading=45),
    Case("flee_climb", _T, (5, 0, 3)),
    Case("circle", _T, (4, 0.178, 0)),
    Case("flee_turn", _T, (5, 0.269, 0)),
    Case("flee_turn_tight", _T, (5, 0.538, 0)),
    Case("flee_climb_cross", _T, (7.07, 0, 2), heading=45),
    Case("fast_flee_dive", _T, (6, 0, -2)),
    Case("flee_dive", _T, (5, 0, -3)),
    Case("far_spiral_descend", (200, 0, WORK_ALT), (12, 0.538, -1.5), min_agl=0.75),
    Case("fast_diag_flee", (60, 15, WORK_ALT), (14.1, 0, 0), heading=45),
    Case("fast_flee_ground", (100, 0, 0.75), (15, 0.108, 0), min_agl=0.75),
    Case("far_static", (200, 0, 0.75), min_agl=0.75),
    Case("far_flee", (200, 0, 0.75), (10, 0, 0), min_agl=0.75),
    Case("far_turn_wide", (200, 0, 0.75), (10, 0.269, 0), min_agl=0.75),
    Case("far_turn", (200, 0, 0.75), (10, 0.538, 0), min_agl=0.75),
    Case("far_turn_fast", (200, 0, 0.75), (15, 1.077, 0), min_agl=0.75),
    Case("far_turn_tight", (200, 0, 0.75), (10, 2.692, 0), min_agl=0.75),
    Case("cruise_straight", (100, 0, 0.75), (9, 0, 0)),
]


def _clamp(x, lim):
    return min(max(x, -lim), lim)


def _wrap_pi(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            f = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + f * (ys[i] - ys[i - 1])
    return ys[-1]


def _drag_accel(v):
    """水平速度 v 下的阻力加速度大小：量測範圍內按穩態前傾角，範圍外按 v² 延伸。"""
    v_top, th_top = DRAG_POLAR[-1]
    if v <= v_top:
        th = _interp(v, [p[0] for p in DRAG_POLAR], [p[1] for p in DRAG_POLAR])
        return G * math.tan(math.radians(th))
    return G * math.tan(math.radians(th_top)) * (v / v_top) ** 2


def _body_h_to_ned(f, r, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return f * c - r * s, f * s + r * c


def _ned_to_body_h(n, e, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return n * c + e * s, -n * s + e * c


class Vehicle:
    """速度命令 → 一階速度響應（含推力傾角上限與阻力）；姿態由加速度合成。"""

    def __init__(self):
        self.pos = [0.0, 0.0, -WORK_ALT]
        self.vel = [0.0, 0.0, 0.0]
        self.yaw = 0.0
        self.yaw_rate = 0.0
        self.acc = [0.0, 0.0, 0.0]
        self._pitch_prev = 0.0
        self._dt_prev = 0.0

    def step(self, cmd, dt, substeps=4):
        self._pitch_prev, self._dt_prev = self.attitude()["pitch"], dt
        h = dt / substeps
        for _ in range(substeps):
            v_up = min(max(cmd["v_up"], -V_DN_MAX), V_UP_MAX)
            vn_c, ve_c = _body_h_to_ned(cmd["v_fwd"], cmd["v_right"], self.yaw)
            v_cmd = (vn_c, ve_c, -v_up)
            tau_v = TAU_VDN if v_cmd[2] > self.vel[2] else TAU_VUP
            a = [(v_cmd[0] - self.vel[0]) / TAU_VXY, (v_cmd[1] - self.vel[1]) / TAU_VXY,
                 (v_cmd[2] - self.vel[2]) / tau_v]
            # 傾角上限夾在推力上：推力同時要抵銷阻力與產生淨加速度
            v_h = math.hypot(self.vel[0], self.vel[1])
            k_v = _drag_accel(v_h) / max(v_h, 1e-6)
            a_drag = (-k_v * self.vel[0], -k_v * self.vel[1])
            th = [a[0] - a_drag[0], a[1] - a_drag[1]]
            mag = math.hypot(*th)
            if mag > A_H_MAX:
                th = [x * A_H_MAX / mag for x in th]
            a[0], a[1] = th[0] + a_drag[0], th[1] + a_drag[1]
            a[2] = _clamp(a[2], A_V_MAX)
            self.acc = a
            for i in range(3):
                self.vel[i] += a[i] * h
                self.pos[i] += self.vel[i] * h
            yr_cmd = _clamp(cmd["yaw_rate"], YAW_RATE_MAX)
            self.yaw_rate += (yr_cmd - self.yaw_rate) / TAU_R * h
            self.yaw = _wrap_pi(self.yaw + self.yaw_rate * h)

    def attitude(self):
        a_fwd, a_rgt = _ned_to_body_h(self.acc[0], self.acc[1], self.yaw)
        v_h = math.hypot(self.vel[0], self.vel[1])
        v_fwd, _ = _ned_to_body_h(self.vel[0], self.vel[1], self.yaw)
        a_drag = _drag_accel(v_h) / max(v_h, 1e-6) * v_fwd
        pitch = -math.atan2(a_fwd + a_drag, G)
        roll = math.atan2(a_rgt, G)
        rate = (pitch - self._pitch_prev) / self._dt_prev if self._dt_prev else 0.0
        return {"roll": roll, "pitch": pitch, "yaw": self.yaw, "pitchspeed": rate}


def target_pose(c: Case, t):
    """目標在時刻 t 的 (位置 NED, 偏航角, 速度 NED)。"""
    psi0 = -math.radians(c.heading)
    vf, vl, vu = c.vel
    om = -vl / TARGET_LEVER
    n0, e0, d0 = c.pos[0], -c.pos[1], -c.pos[2]
    psi = psi0 + om * t
    if abs(om) < 1e-12:
        vn, ve = vf * math.cos(psi0) + vl * math.sin(psi0), vf * math.sin(psi0) - vl * math.cos(psi0)
        n, e = n0 + vn * t, e0 + ve * t
    else:
        s0, c0, s1, c1 = math.sin(psi0), math.cos(psi0), math.sin(psi), math.cos(psi)
        n = n0 + (vf * (s1 - s0) + vl * (c0 - c1)) / om
        e = e0 + (vf * (c0 - c1) - vl * (s1 - s0)) / om
        vn, ve = vf * c1 + vl * s1, vf * s1 - vl * c1
    floor = -min(c.min_agl, c.pos[2])
    d = d0 - vu * t
    vd = -vu
    if d > floor:
        d, vd = floor, 0.0
    return (n, e, d), psi, (vn, ve, vd)


def surface_dist(p, tgt_pos, tgt_yaw):
    """點 p 到目標外形（隨偏航旋轉的長方體）的距離，在內部為 0。"""
    dn, de, dd = (p[i] - tgt_pos[i] for i in range(3))
    f, r = _ned_to_body_h(dn, de, tgt_yaw)
    ex = [max(abs(x) - h, 0.0) for x, h in zip((f, r, dd), TARGET_HALF)]
    return math.sqrt(sum(x * x for x in ex))


def _rot_body_to_ned(roll, pitch, yaw):
    cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch),
                              math.sin(pitch), math.cos(yaw), math.sin(yaw))
    return ((cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
            (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
            (-sp, cp * sr, cp * cr))


def _to_sensor(p_ned, veh_pos, R):
    """世界點 → 相機系（x 光軸向前、y 左、z 上）。"""
    d = [p_ned[i] - veh_pos[i] for i in range(3)]
    frd = [R[0][j] * d[0] + R[1][j] * d[1] + R[2][j] * d[2] for j in range(3)]
    x, y, z = frd[0] - CAM_OFFSET_FLU[0], -frd[1] - CAM_OFFSET_FLU[1], -frd[2] - CAM_OFFSET_FLU[2]
    cp, sp = math.cos(MOUNT_PITCH), math.sin(MOUNT_PITCH)
    return cp * x + sp * z, y, -sp * x + cp * z


def detect(veh_pos, att, tgt_pos, tgt_yaw):
    """相機這一幀的目標框（畫幅歸一化），目標中心不在視野內時為 None。"""
    R = _rot_body_to_ned(att["roll"], att["pitch"], att["yaw"])
    xs, ys, zs = _to_sensor(tgt_pos, veh_pos, R)
    if abs(math.atan2(ys, xs)) >= HFOV_HALF or abs(math.atan2(zs, xs)) >= VFOV_HALF:
        return None
    us, vs = [], []
    for sf in (-1, 1):
        for sr in (-1, 1):
            for sd in (-1, 1):
                dn, de = _body_h_to_ned(sf * TARGET_HALF[0], sr * TARGET_HALF[1], tgt_yaw)
                corner = (tgt_pos[0] + dn, tgt_pos[1] + de, tgt_pos[2] + sd * TARGET_HALF[2])
                x, y, z = _to_sensor(corner, veh_pos, R)
                x = max(x, 1e-3)
                us.append(min(max(CX - y / x * FX, 0.0), RES_W))
                vs.append(min(max(CY - z / x * FY, 0.0), RES_H))
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    return {"cx": (u0 + u1) / 2 / RES_W, "cy": (v0 + v1) / 2 / RES_H,
            "w": (u1 - u0) / RES_W, "h": (v1 - v0) / RES_H}


class _Peer:
    """以子程序執行的飛行控制規劃，一行一則 JSON。"""

    def __init__(self, gnc_path, stderr):
        self.p = subprocess.Popen([sys.executable, gnc_path], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=stderr, cwd=os.path.dirname(gnc_path))
        self.buf = b""

    def send(self, obj):
        self.p.stdin.write((json.dumps(obj) + "\n").encode())
        self.p.stdin.flush()

    def recv(self, timeout):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buf:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"GNC {timeout:g} 秒內沒有回應")
            if select.select([self.p.stdout], [], [], left)[0]:
                chunk = os.read(self.p.stdout.fileno(), 65536)
                if not chunk:
                    raise EOFError(f"GNC 結束了（結束碼 {self.p.wait()}）")
                self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def close(self):
        try:
            self.send({"type": "end"})
            self.p.stdin.close()
            self.p.wait(timeout=2)
        except Exception:
            self.p.kill()
            self.p.wait()
        finally:
            self.p.stdout.close()


def _parse_cmd(msg):
    if not isinstance(msg, dict):
        raise ValueError(f"命令不是 JSON 物件：{msg!r}")
    cmd = {}
    for k in ("v_fwd", "v_right", "v_up", "yaw_rate"):
        v = msg.get(k, 0.0)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"命令欄位 {k} 不是有限的數字：{v!r}")
        cmd[k] = float(v)
    return cmd


def run_case(c: Case, gnc_path=None, trace_path=None, stderr=None):
    """跑一個情境，回傳結果 dict（passed、reason、t_contact、cpa…）。"""
    gnc_path = os.path.abspath(gnc_path or os.path.join(HERE, "gnc.py"))
    veh = Vehicle()
    peer = _Peer(gnc_path, stderr if stderr is not None else subprocess.DEVNULL)
    trace = open(trace_path, "w") if trace_path else None
    if trace:
        trace.write("t,n,e,d,yaw,tn,te,td,det_cx,det_cy,det_w,det_h,v_fwd,v_right,v_up,yaw_rate,dist\n")
    res = {"case": c.name, "passed": False, "reason": "timeout", "t_contact": None,
           "first_det": None, "cpa": math.inf}
    t, k, passive = 0.0, 0, False
    deadline = time.monotonic() + WALL_LIMIT
    try:
        peer.send(INIT)
        while t < DURATION:
            if time.monotonic() > deadline:
                raise TimeoutError(f"這個情境的執行時間超過 {WALL_LIMIT:g} 秒")
            tgt_pos, tgt_yaw, tgt_vel = target_pose(c, t)
            att = veh.attitude()
            det = detect(veh.pos, att, tgt_pos, tgt_yaw)
            if det is not None and res["first_det"] is None:
                res["first_det"] = round(t, 3)
            peer.send({"type": "tick", "t": t, "det": det, "att": att,
                       "pos_ned": list(veh.pos), "vel_ned": list(veh.vel)})
            cmd = _parse_cmd(peer.recv(10.0 if k == 0 else 5.0))
            # 接觸：這一拍 [t, t+dt] 內細分取樣，載具按目前速度外推
            surf = math.inf
            for i in range(9):
                tau = DT * i / 8
                p = [veh.pos[j] + veh.vel[j] * tau for j in range(3)]
                tp, ty, _ = target_pose(c, t + tau)
                surf = min(surf, surface_dist(p, tp, ty))
            res["cpa"] = min(res["cpa"], surf)
            rel = [tgt_pos[j] - veh.pos[j] for j in range(3)]
            dist = math.sqrt(sum(x * x for x in rel))
            if trace:
                dv = [det[x] for x in ("cx", "cy", "w", "h")] if det else ["", "", "", ""]
                trace.write(",".join(f"{x:.4f}" if isinstance(x, float) else str(x) for x in (
                    t, *veh.pos, veh.yaw, *tgt_pos, *dv, cmd["v_fwd"], cmd["v_right"],
                    cmd["v_up"], cmd["yaw_rate"], dist)) + "\n")
            if surf > 0.0:
                passive = False
            elif not passive:
                # 以剛碰到的那一刻判斷：載具幾乎沒在接近、是目標自己接觸來的，整段接觸都不算
                u = [x / max(dist, 1e-9) for x in rel]
                veh_closing = sum(veh.vel[j] * u[j] for j in range(3))
                tgt_closing = -sum(tgt_vel[j] * u[j] for j in range(3))
                if veh_closing < 1.0 and tgt_closing > 0.5:
                    passive = True
                else:
                    res["t_contact"] = round(t, 3)
                    res["reason"] = "contact"
                    break
            veh.step(cmd, DT)
            t = (k + 1) * DT
            k += 1
            if veh.pos[2] > 0.0:
                res["reason"] = f"墜地（t={t:.2f}s）"
                break
    except (TimeoutError, EOFError, ValueError, BrokenPipeError) as e:
        res["reason"] = f"error: {e}"
    finally:
        peer.close()
        if trace:
            trace.close()
    if res["reason"] == "timeout":
        res["reason"] = f"{DURATION:g} 秒內未接觸"
    if res["first_det"] is None and res["reason"] == "contact":
        res["reason"] = "接觸但從未偵測到目標"
    res["passed"] = res["reason"] == "contact"
    res["cpa"] = round(res["cpa"], 3)
    return res


def main():
    ap = argparse.ArgumentParser(description="多旋翼視覺攔截模擬台")
    ap.add_argument("cases", nargs="*", help="情境名，不給 = 全部")
    ap.add_argument("--gnc", default=os.path.join(HERE, "gnc.py"), help="GNC 程式路徑")
    ap.add_argument("--trace", metavar="DIR", help="每個情境逐拍紀錄寫成 DIR/<情境>.csv，GNC 的 stderr 寫成 DIR/<情境>.stderr")
    args = ap.parse_args()
    by_name = {c.name: c for c in CASES}
    bad = [n for n in args.cases if n not in by_name]
    if bad:
        ap.error(f"沒有這些情境：{bad}；可用：{', '.join(by_name)}")
    cases = [by_name[n] for n in args.cases] or CASES
    if args.trace:
        os.makedirs(args.trace, exist_ok=True)
    n_pass = 0
    for c in cases:
        err = open(os.path.join(args.trace, c.name + ".stderr"), "w") if args.trace else None
        r = run_case(c, args.gnc, args.trace and os.path.join(args.trace, c.name + ".csv"), err)
        if err:
            err.close()
        n_pass += r["passed"]
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {c.name:20s} {r['reason']:24s} "
              f"接觸 {r['t_contact'] if r['t_contact'] is not None else '—':>7}  "
              f"最近 {r['cpa']:7.2f} m  首次偵測 {r['first_det'] if r['first_det'] is not None else '—'}",
              flush=True)
    print(f"通過 {n_pass}/{len(cases)}")
    return 0 if n_pass == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
