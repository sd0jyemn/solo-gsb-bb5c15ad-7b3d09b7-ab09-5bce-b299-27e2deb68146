import pytest

from app.analyzer import analyze_track
from app.geo import Point


def pts(spec):
    """spec: (lon, lat, epoch_seconds) 列表"""
    return [Point(lon=lon, lat=lat, ts=t) for lon, lat, t in spec]


# 家附近停留（含一次 1200s 采样间断）-> 移动 -> 公司停留
TRACK = pts([
    (116.3910, 39.9070, 0),
    (116.3912, 39.9071, 120),
    (116.3908, 39.9069, 240),
    (116.3911, 39.9072, 1440),    # 停留区内的采样间断
    (116.3950, 39.9100, 1800),    # 驶离
    (116.4013, 39.9172, 2400),    # 进入公司前的最后一个移动点（距公司锚点 >100m）
    (116.4020, 39.9180, 2700),    # 进入公司
    (116.4022, 39.9181, 3000),
    (116.4018, 39.9179, 3300),
])


def test_detects_two_stays_with_ranges_and_center():
    r = analyze_track(TRACK, 100.0, 300.0, 300.0)
    assert r["summary"]["stay_count"] == 2

    stay1, stay2 = r["stays"]
    assert (stay1["start_index"], stay1["end_index"]) == (0, 3)
    assert stay1["duration_s"] == 1440
    assert stay1["point_count"] == 4
    assert stay1["enter_coords"] == [116.3910, 39.9070]
    assert stay1["leave_coords"] == [116.3911, 39.9072]
    assert stay1["radius_m"] <= 100.0

    assert (stay2["start_index"], stay2["end_index"]) == (6, 8)
    assert stay2["duration_s"] == 600
    assert "center" in stay2 and "lon" in stay2["center"]


def test_gap_inside_stay_recorded_not_splitting():
    r = analyze_track(TRACK, 100.0, 300.0, 300.0)
    stay1 = r["stays"][0]
    assert len(stay1["gaps"]) == 1
    gap = stay1["gaps"][0]
    assert gap["duration_s"] == 1200
    assert gap["segment_type"] == "stay"
    assert gap["boundary"] is False
    assert r["summary"]["in_stay_gap_seconds"] == 1200


def test_moves_cover_non_stay_points():
    r = analyze_track(TRACK, 100.0, 300.0, 300.0)
    assert len(r["moves"]) == 1
    move = r["moves"][0]
    assert (move["start_index"], move["end_index"]) == (4, 5)
    assert move["distance_m"] > 0


def test_totals_and_gap_list():
    r = analyze_track(TRACK, 100.0, 300.0, 300.0)
    s = r["summary"]
    assert s["point_count"] == 9
    assert s["total_duration_s"] == 3300
    assert s["total_distance_m"] == pytest.approx(
        s["moving_distance_m"] + s["stay_distance_m"]
    )
    # 三次间断：停留区内 1200s、停留->移动边界 360s、移动区内 600s
    assert s["gap_count"] == 3
    assert s["max_gap_seconds"] == 1200


def test_short_pause_is_not_stay():
    track = pts([
        (0.0, 0.0, 0),
        (0.0, 0.0, 100),     # 只停 100s < 300s
        (0.01, 0.01, 400),
    ])
    r = analyze_track(track, 100.0, 300.0, 300.0)
    assert r["summary"]["stay_count"] == 0
    assert len(r["moves"]) == 1
    assert r["moves"][0]["point_count"] == 3


def test_threshold_zero_allows_single_timestamp_stay():
    track = pts([
        (0.0, 0.0, 0),
        (0.0, 0.0001, 60),
        (0.01, 0.01, 120),
    ])
    r = analyze_track(track, 100.0, 0.0, 300.0)
    # min_stay_seconds=0：即使单点候选（时间跨度 0）也允许成为停留
    assert r["summary"]["stay_count"] == 2
    assert r["stays"][0]["point_count"] == 2
    assert r["stays"][1]["point_count"] == 1


def test_boundary_gap_labeled_between():
    # 停留 -> 间隔 1h -> 远处移动点
    track = pts([
        (0.0, 0.0, 0),
        (0.0001, 0.0, 600),
        (1.0, 1.0, 4200),
    ])
    r = analyze_track(track, 100.0, 300.0, 300.0)
    boundary = [g for g in r["gaps"] if g["boundary"]]
    assert len(boundary) == 1
    assert boundary[0]["segment_type"] == "between"
    assert boundary[0]["duration_s"] == 3600


def test_unsorted_input_raises():
    track = pts([
        (0.0, 0.0, 100),
        (0.0, 0.0, 0),
    ])
    with pytest.raises(ValueError, match="升序"):
        analyze_track(track, 100.0, 300.0, 300.0)


def test_anchor_distance_prevents_chain_drift():
    # 每步都小于阈值，但整体离锚点越来越远：不应被无限合并
    track = pts([
        (0.0, 0.0, 0),
        (0.0004, 0.0, 60),     # ~44m，并入
        (0.0008, 0.0, 120),    # ~89m，并入（到锚点仍 <=100m）
        (0.0012, 0.0, 180),    # ~133m 到锚点 -> 闭合于索引 2，另起候选
    ])
    r = analyze_track(track, 100.0, 0.0, 300.0)
    first = r["stays"][0] if r["stays"] else r["moves"][0]
    assert first["end_index"] == 2


def test_invalid_arguments():
    with pytest.raises(ValueError, match="至少需要"):
        analyze_track([Point(0, 0, 0)], 100.0, 300.0, 300.0)
    with pytest.raises(ValueError, match="不能为负"):
        analyze_track(
            [Point(0, 0, 0), Point(0.001, 0, 60)], -1, 300.0, 300.0
        )
