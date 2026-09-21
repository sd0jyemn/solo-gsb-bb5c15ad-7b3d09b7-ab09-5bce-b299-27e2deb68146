# 轨迹停留分析 API（FastAPI + Docker）

提交一条带时间戳、经纬度的**有序轨迹**以及距离阈值与最短停留时长阈值，服务按
**Haversine 距离**对流式合并后的连续点进行分析，识别每个停留区段的**进入点、离开点、
中心点、原始点范围、停留时长**，并检测**跨采样间断**（设备长时间无采样但空间未离开）。
另提供 **GeoJSON** 输出与**总里程、停留次数**等统计。

- Web 框架：FastAPI（自动 OpenAPI / Swagger 文档）
- 核心算法：单次前向扫描，时间复杂度 O(n)
- 交付：`Dockerfile` + `docker-compose.yml`，一键启动，自带健康检查

---

## 1. 一键启动

```bash
# 在仓库根目录
docker compose up -d --build
```

服务监听 `http://localhost:8000`：

| 地址 | 说明 |
| --- | --- |
| `GET /health` | 健康检查 |
| `POST /api/v1/analyze` | 停留分析（JSON） |
| `POST /api/v1/analyze.geojson` | 停留分析（GeoJSON FeatureCollection） |
| `GET /docs` | Swagger 交互文档 |
| `GET /openapi.json` | OpenAPI Schema |

停止：

```bash
docker compose down
```

不使用 Compose：

```bash
docker build -t stay-analysis-api .
docker run --rm -p 8000:8000 stay-analysis-api
```

### 本地开发（无需 Docker）

```bash
python3 -m pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
python3 -m pytest          # 运行测试
```

---

## 2. 快速体验

仓库内置示例轨迹（家停留含一次 31 分钟采样间断 → 移动 → 短暂停靠（不算停留）→ 公司停留）：

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d @examples/sample_request.json
```

输出（完整内容见 `examples/sample_response.json`）：

```
=== 总览 ===
总里程:       1688.0 m
停留次数:     2
停留总时长:   2700 s
采样间断次数: 6（其中停留区内 1860 s）

停留 #1: 2026-09-21T08:00:00Z -> 2026-09-21T08:35:00Z (2100s, 4 点, 原始索引 0..3)
    中心点: (116.391025, 39.907050), 散布半径 25.4 m
    跨采样间断: 1860 s (索引 2->3)
停留 #2: 2026-09-21T09:15:00Z -> 2026-09-21T09:25:00Z (600s, 3 点, 原始索引 11..13)
    中心点: (116.402000, 39.918000), 散布半径 20.4 m
```

```bash
# GeoJSON（可直接拖进 geojson.io / QGIS 查看）
curl -X POST http://localhost:8000/api/v1/analyze.geojson \
  -H 'Content-Type: application/json' \
  -d @examples/sample_request.json -o result.geojson

# 纯标准库的命令行示例脚本
python3 examples/call_api.py                       # JSON 摘要
python3 examples/call_api.py my_track.json geojson # GeoJSON 全量
```

---

## 3. 停留识别算法

```
anchor = 第 0 个点
for 轨迹中的每个后续点 p:                      # 单次前向扫描 O(n)
    if haversine(anchor, p) <= 距离阈值:
        将 p 并入当前候选区段
    else:
        闭合当前候选；anchor = p，另起候选

对每个候选:
    if (末点时间 - 首点时间) >= 最短停留时长:   → 停留区段（stay）
    else:                                      → 移动点（相邻候选合并为移动区段 move）
```

要点说明：

1. **锚点距离，防止链式漂移**：始终比较"当前候选第一个点（进入点）"与新点的距离，
   而不是与前一个点比较。否则沿同方向每步只移动几十米的点会被无限串进同一次停留。
2. **跨采样间断不切断停留**：相邻两点时间间隔超过 `gap_seconds` 时，不新建区段，
   而是在所在区段的 `gaps` 中记录一条间断（含起止时间、时长、两端坐标）。
   这正是"长时间没有采样，但人没有离开"的情形。
3. **短暂停靠不算停留**：空间没动但时间跨度不足 `min_stay_seconds` 的候选归入移动。
4. **边界间断**：恰好落在停留/移动区段分界处的长间隔，标记为
   `segment_type = "between"`、`boundary = true`。
5. 严格大于阈值才判定为间断；`min_stay_seconds = 0` 时允许单点、零时长停留。

---

## 4. 请求

`POST /api/v1/analyze`（两个分析端点请求体相同）

```json
{
  "distance_threshold_m": 100.0,
  "min_stay_seconds": 300,
  "gap_seconds": 300,
  "sort_points": false,
  "points": [
    {"lon": 116.3910, "lat": 39.9070, "time": "2026-09-21T08:00:00Z"},
    {"lon": 116.3912, "lat": 39.9071, "time": 1789999320000}
  ]
}
```

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `points` | array | 必填，≥2 个 | 轨迹点，**默认要求按时间升序**；乱序返回 400 |
| `points[].lon` / `lat` | float | 必填 | WGS84 经纬度，范围自动校验 |
| `points[].time` | string/number | 必填 | ISO 8601 字符串（`Z`/偏移/无时区按 UTC），或 epoch **秒 / 毫秒**数字（≥1e11 视为毫秒） |
| `distance_threshold_m` | float | `100.0` | 与进入锚点的距离阈值（米），≤ 阈值即合并 |
| `min_stay_seconds` | float | `300` | 最短停留时长（秒），候选首末点时间跨度达到它才算停留 |
| `gap_seconds` | float | `300` | 采样间断阈值（秒），相邻点间隔严格大于它即记录一次间断 |
| `sort_points` | bool | `false` | 为 `true` 时服务端先按时间排序再分析（摘要中 `input_was_sorted=false`） |

错误码：`400` 轨迹未按时间升序；`422` 字段校验失败（经纬度越界、点数不足、时间无法解析等）。

---

## 5. JSON 响应

```json
{
  "summary": {
    "point_count": 14,
    "total_distance_m": 1688.018,        // 总里程（全部相邻点 Haversine 之和）
    "total_duration_s": 5100.0,
    "moving_distance_m": 1523.802,
    "stay_distance_m": 164.215,
    "stay_count": 2,                     // 停留次数
    "total_stay_seconds": 2700.0,        // 停留总时长
    "gap_count": 6,
    "total_gap_seconds": 3660.0,
    "in_stay_gap_seconds": 1860.0,       // 停留区内的间断时长合计
    "max_gap_seconds": 1860.0,
    "distance_threshold_m": 100.0,
    "min_stay_seconds": 300.0,
    "gap_seconds": 300.0,
    "input_was_sorted": true
  },
  "stays": [
    {
      "type": "stay",
      "seq": 1,
      "start_index": 0,                  // 原始点范围（含端点）
      "end_index": 3,
      "enter_time": "2026-09-21T08:00:00Z",
      "leave_time": "2026-09-21T08:35:00Z",
      "duration_s": 2100.0,              // 停留时长
      "point_count": 4,
      "distance_m": 164.215,
      "center": {"lon": 116.391025, "lat": 39.90705}, // 中心点（等权平均）
      "radius_m": 25.4,                  // 各原始点到中心点的最大距离
      "enter_coords": [116.391, 39.907],
      "leave_coords": [116.3911, 39.9072],
      "gaps": [
        {
          "from_index": 2, "to_index": 3,
          "segment_type": "stay", "boundary": false,
          "start_time": "2026-09-21T08:04:00Z",
          "end_time": "2026-09-21T08:35:00Z",
          "duration_s": 1860.0,
          "distance_m": 33.4,
          "from_coords": [116.3908, 39.9069],
          "to_coords": [116.3911, 39.9072]
        }
      ]
    }
  ],
  "moves": [ /* 移动区段，字段同区段公共部分，无 center/radius */ ],
  "gaps": [ /* 全部间断（stay/move 区内 + between 边界），按轨迹顺序 */ ]
}
```

所有坐标均为 GeoJSON 序：`[经度, 纬度]`；所有时间输出统一为 UTC（`...Z`）。

---

## 6. GeoJSON 响应

`POST /api/v1/analyze.geojson` 返回 `application/geo+json` 的 FeatureCollection，
每个 Feature 的 `properties.geometry_kind` 为：

| geometry_kind | 几何 | 含义 |
| --- | --- | --- |
| `stay_center` | Point | 停留中心点（含时长、半径、点数） |
| `stay_extent` | LineString | 停留区段的原始点范围 |
| `move` | LineString | 移动区段的原始点范围 |
| `enter` / `leave` | Point | 停留进入点 / 离开点 |
| `gap` | LineString | 跨采样间断（`segment_type` 标明位于 stay/move/between） |

可直接在 <https://geojson.io> 或 QGIS 中打开 `examples/sample_response.geojson`。

---

## 7. 项目结构

```
.
├── app/
│   ├── main.py          # FastAPI 路由、异常处理
│   ├── schemas.py       # 请求/响应模型、时间字段解析
│   ├── analyzer.py      # 流式停留识别核心
│   ├── geo.py           # Haversine / 中心点 / 半径
│   └── geojson.py       # GeoJSON 转换
├── tests/               # pytest：geo、算法、HTTP 接口（共 22 个用例）
├── examples/
│   ├── sample_request.json
│   ├── sample_response.json
│   ├── sample_response.geojson
│   └── call_api.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── requirements-dev.txt
```

## 8. 注意事项与边界

- 坐标按 **WGS84** 处理；中心点为经纬度等权平均，适用于停留点这种小跨度集合，
  未处理跨越 ±180° 经线与极区的情况。
- 里程为相邻采样点大圆距离之和；采样间隔越大，相对真实轨迹越偏低（折线近似）。
- 服务本身无状态、无持久化，可水平扩容；未内置鉴权与限流，公网部署请放在网关之后。
- 超长轨迹建议分批调用；当前实现为一次性请求/响应。
