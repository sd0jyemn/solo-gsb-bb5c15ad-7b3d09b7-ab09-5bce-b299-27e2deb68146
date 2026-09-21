"""流式停留点识别核心算法。

规则
----
1. 轨迹必须按时间升序；
2. 以每个区段的"第一个点"为锚点（进入点），逐点用 Haversine 距离判断：
   到锚点距离 <= distance_threshold_m 即并入当前停留候选；否则先闭合当前候选，
   再从该点开始一个新候选（单次前向扫描，O(n)）；
3. 候选内"首点 -> 末点"的时间跨度 >= min_stay_seconds 才判定为停留；
   否则候选内的点视为移动（连续的非停留候选会合并成一个移动区段）；
4. 跨采样间断（相邻点时间间隔 > gap_seconds）不会切分停留，而是作为
   ``gaps`` 记录挂在所在区段上（``segment_type`` 标明 stay/move）；
   边界上的间断标记为 boundary；
5. 时间跨度为 0（首末点同一时刻）的候选不可能满足最小停留时长（阈值 > 0 时）。
"""
from __future__ import annotations

from typing import Any

from .geo import Point, centroid, haversine_m, radius_m


def analyze_track(
    points: list[Point],
    distance_threshold_m: float,
    min_stay_seconds: float,
    gap_seconds: float,
    sorted_input: bool = True,
) -> dict[str, Any]:
    """分析轨迹并返回停留 / 移动区段、间断与统计信息。"""
    n = len(points)
    if n < 2:
        raise ValueError("至少需要 2 个轨迹点")
    if distance_threshold_m < 0:
        raise ValueError("distance_threshold_m 不能为负")
    if min_stay_seconds < 0:
        raise ValueError("min_stay_seconds 不能为负")
    if gap_seconds < 0:
        raise ValueError("gap_seconds 不能为负")

    # ---- 预计算每一条相邻点边（leg）的距离与时间间隔 ----
    leg_dist: list[float] = [0.0] * (n - 1)
    leg_dt: list[float] = [0.0] * (n - 1)
    for i in range(n - 1):
        a, b = points[i], points[i + 1]
        dt = b.ts - a.ts
        if sorted_input and dt < 0:
            raise ValueError(
                f"轨迹必须按时间升序：第 {i} 点晚于第 {i + 1} 点"
            )
        leg_dist[i] = haversine_m(a.lon, a.lat, b.lon, b.lat)
        leg_dt[i] = dt

    total_distance_m = sum(leg_dist)
    total_duration_s = points[-1].ts - points[0].ts
    all_gap_legs = [i for i, dt in enumerate(leg_dt) if dt > gap_seconds]

    # ---- 单次前向扫描：流式合并连续近邻点 ----
    runs: list[tuple[int, int]] = []  # [start, end]，闭区间
    start = 0
    anchor = points[0]
    for i in range(1, n):
        d = haversine_m(anchor.lon, anchor.lat, points[i].lon, points[i].lat)
        if d <= distance_threshold_m:
            continue  # 并入当前候选
        runs.append((start, i - 1))
        start = i
        anchor = points[i]
    runs.append((start, n - 1))

    def make_gap(leg_index: int, owner: str, boundary: bool) -> dict[str, Any]:
        i = leg_index
        a, b = points[i], points[i + 1]
        return {
            "from_index": i,
            "to_index": i + 1,
            "segment_type": owner,
            "boundary": boundary,
            "start_time": a.ts,
            "end_time": b.ts,
            "duration_s": leg_dt[i],
            "distance_m": leg_dist[i],
            "from_coords": a.as_coords(),
            "to_coords": b.as_coords(),
        }

    stays: list[dict[str, Any]] = []
    moves: list[dict[str, Any]] = []

    def build_segment(run_list: list[tuple[int, int]], kind: str, seq: int) -> dict[str, Any]:
        s = run_list[0][0]
        e = run_list[-1][1]
        seg_points = points[s : e + 1]
        seg_legs = range(s, e)  # 区段内部的边
        gaps = [
            make_gap(i, owner=kind, boundary=False)
            for i in seg_legs
            if leg_dt[i] > gap_seconds
        ]
        distance = sum(leg_dist[i] for i in seg_legs)
        return {
            "type": kind,
            "seq": seq,
            "start_index": s,
            "end_index": e,
            "enter_time": points[s].ts,
            "leave_time": points[e].ts,
            "duration_s": points[e].ts - points[s].ts,
            "point_count": e - s + 1,
            "distance_m": distance,
            "gaps": gaps,
        }

    # ---- 候选判定停留；相邻的非停留候选合并成移动区段 ----
    pending_move: list[tuple[int, int]] = []
    timeline: list[dict[str, Any]] = []

    def flush_move() -> None:
        if not pending_move:
            return
        seg = build_segment(pending_move, "move", len(moves) + 1)
        moves.append(seg)
        timeline.append(seg)
        pending_move.clear()

    for rs, re_ in runs:
        duration = points[re_].ts - points[rs].ts
        if duration >= min_stay_seconds:
            flush_move()
            seg_points = points[rs : re_ + 1]
            c_lon, c_lat = centroid(seg_points)
            enter, leave = points[rs], points[re_]
            seg = {
                "type": "stay",
                "seq": len(stays) + 1,
                "start_index": rs,
                "end_index": re_,
                "enter_time": enter.ts,
                "leave_time": leave.ts,
                "duration_s": duration,
                "point_count": re_ - rs + 1,
                "distance_m": sum(leg_dist[i] for i in range(rs, re_)),
                "center": {"lon": c_lon, "lat": c_lat},
                "radius_m": radius_m(seg_points, c_lon, c_lat),
                "enter_coords": enter.as_coords(),
                "leave_coords": leave.as_coords(),
                "gaps": [
                    make_gap(i, owner="stay", boundary=False)
                    for i in range(rs, re_)
                    if leg_dt[i] > gap_seconds
                ],
            }
            stays.append(seg)
            timeline.append(seg)
        else:
            pending_move.append((rs, re_))
    flush_move()

    timeline.sort(key=lambda x: x["start_index"])

    # ---- 区段边界上的间断（两个相邻区段之间）----
    boundary_gaps: list[dict[str, Any]] = []
    for prev_seg, next_seg in zip(timeline, timeline[1:]):
        leg_index = prev_seg["end_index"]
        if leg_dt[leg_index] > gap_seconds:
            boundary_gaps.append(
                make_gap(
                    leg_index,
                    owner="between",
                    boundary=True,
                )
            )

    gaps_all: list[dict[str, Any]] = []
    for seg in timeline:
        gaps_all.extend(seg["gaps"])
    gaps_all.extend(boundary_gaps)
    gaps_all.sort(key=lambda g: g["from_index"])

    stay_distance = sum(s["distance_m"] for s in stays)
    stay_gap_time = sum(
        g["duration_s"] for s in stays for g in s["gaps"]
    )
    total_gap_time = sum(g["duration_s"] for g in gaps_all)
    max_gap = max((leg_dt[i] for i in all_gap_legs), default=0.0)

    summary = {
        "point_count": n,
        "total_distance_m": round(total_distance_m, 3),
        "total_duration_s": round(total_duration_s, 3),
        "moving_distance_m": round(total_distance_m - stay_distance, 3),
        "stay_distance_m": round(stay_distance, 3),
        "stay_count": len(stays),
        "total_stay_seconds": round(
            sum(s["duration_s"] for s in stays), 3
        ),
        "gap_count": len(gaps_all),
        "total_gap_seconds": round(total_gap_time, 3),
        "in_stay_gap_seconds": round(stay_gap_time, 3),
        "max_gap_seconds": round(max_gap, 3),
        "distance_threshold_m": distance_threshold_m,
        "min_stay_seconds": min_stay_seconds,
        "gap_seconds": gap_seconds,
        "input_was_sorted": bool(sorted_input),
    }

    return {"summary": summary, "stays": stays, "moves": moves, "gaps": gaps_all}
