#!/usr/bin/env python3
"""命令行示例：读取轨迹 JSON，调用停留分析接口并打印结果。

用法:
    python examples/call_api.py                    # 默认使用同目录 sample_request.json
    python examples/call_api.py track.json geojson # 第二个参数: json | geojson
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"


def call(payload_path: Path, output_kind: str = "json") -> dict:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    endpoint = (
        f"{BASE_URL}/api/v1/analyze.geojson"
        if output_kind == "geojson"
        else f"{BASE_URL}/api/v1/analyze"
    )
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    here = Path(__file__).resolve().parent
    payload_path = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "sample_request.json"
    output_kind = sys.argv[2] if len(sys.argv) > 2 else "json"

    data = call(payload_path, output_kind)

    if output_kind == "geojson":
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    summary = data["summary"]
    print("=== 总览 ===")
    print(f"总里程:       {summary['total_distance_m']:.1f} m")
    print(f"停留次数:     {summary['stay_count']}")
    print(f"停留总时长:   {summary['total_stay_seconds']:.0f} s")
    print(f"采样间断次数: {summary['gap_count']}（其中停留区内 "
          f"{summary['in_stay_gap_seconds']:.0f} s）")
    print()
    for s in data["stays"]:
        c = s["center"]
        print(
            f"停留 #{s['seq']}: {s['enter_time']} -> {s['leave_time']} "
            f"({s['duration_s']:.0f}s, {s['point_count']} 点, "
            f"原始索引 {s['start_index']}..{s['end_index']})"
        )
        print(f"    中心点: ({c['lon']:.6f}, {c['lat']:.6f}), "
              f"散布半径 {s['radius_m']:.1f} m")
        for g in s["gaps"]:
            print(f"    跨采样间断: {g['duration_s']:.0f} s "
                  f"(索引 {g['from_index']}->{g['to_index']})")


if __name__ == "__main__":
    main()
