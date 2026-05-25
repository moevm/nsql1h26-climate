"""
LETI Climate Benchmark
======================
1. Seeds InfluxDB and PostgreSQL with identical test data.
2. Runs 4 example queries 50 times each (each run targets a different element).
3. Saves a histogram PNG per query to RESULTS_DIR.

Measurements / tables match the data-model wiki exactly.
"""

import itertools
import json
import logging
import math
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import psycopg2
import psycopg2.extras
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── environment ──────────────────────────────────────────────────────────────
INFLUX_URL    = os.getenv("INFLUX_URL",    "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN",  "leti-benchmark-token-2026")
INFLUX_ORG    = os.getenv("INFLUX_ORG",    "leti")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "climate")
PG_DSN        = os.getenv("PG_DSN", "postgresql://leti:leti_pass@localhost:5432/climate")
RESULTS_DIR   = Path(os.getenv("RESULTS_DIR", "/results"))
N_RUNS        = 50

# ── reference data (mirrors leti_climate_prototipe/backend/app/seed.py) ─────
BUILDINGS = [
    {"id": "bldg-1", "name": "Корпус 1 (Главный)",      "address": "ул. Проф. Попова, 5",  "floors_count": 5},
    {"id": "bldg-2", "name": "Корпус 2",                 "address": "Аптекарский пр., 5",   "floors_count": 4},
    {"id": "bldg-3", "name": "Корпус 3",                 "address": "Аптекарский пр., 3",   "floors_count": 4},
    {"id": "bldg-4", "name": "Корпус 4",                 "address": "ул. Проф. Попова, 5",  "floors_count": 3},
    {"id": "bldg-5", "name": "Корпус 5",                 "address": "ул. Проф. Попова, 5",  "floors_count": 3},
    {"id": "bldg-L", "name": "Корпус Л (Лабораторный)", "address": "ул. Проф. Попова, 5",  "floors_count": 3},
    {"id": "bldg-M", "name": "Корпус М (Малый)",         "address": "пр. Медиков, 5",       "floors_count": 2},
    {"id": "bldg-A", "name": "АБК (Административный)",  "address": "пр. Медиков, 5",       "floors_count": 3},
]
ROOM_TYPES     = ["Аудитория", "Лаборатория", "Кабинет", "Деканат",
                  "Библиотека", "Серверная", "Столовая", "Спортзал"]
METRIC_TYPES   = ["temperature", "humidity", "co2"]
SENSOR_MODELS  = {"temperature": "SHT31-D", "humidity": "DHT22", "co2": "MH-Z19B"}
SENSOR_STATUSES = ["Active", "Active", "Active", "Active", "Warning", "Error"]


def _rand_value(metric: str, hour: int) -> float:
    if metric == "temperature":
        return round(22.0 + 2 * math.sin(math.pi * hour / 12) + random.uniform(-0.5, 0.5), 1)
    if metric == "humidity":
        return round(50.0 + 5 * math.sin(math.pi * hour / 12) + random.uniform(-2, 2), 1)
    if metric == "co2":
        occupied = 1 if 8 <= hour <= 18 else 0
        return round(400 + 300 * occupied + random.uniform(-20, 20), 1)
    return 0.0


# ════════════════════════════════════════════════════════════════════════════
#  INFLUXDB  SEED
# ════════════════════════════════════════════════════════════════════════════

def seed_influx() -> list[dict]:
    """Write all entities and 24 h of readings. Returns sensor metadata list."""
    log.info("=== Seeding InfluxDB ===")
    rng = random.Random(42)
    now   = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now - timedelta(hours=24)
    meta_ts = now - timedelta(days=30)

    sensors_meta: list[dict] = []
    points: list[Point] = []

    for b in BUILDINGS:
        bdata = {**b, "status": "Active", "deleted": False}
        # measurement=buildings  tags: building_id  fields: json
        points.append(
            Point("buildings")
            .tag("building_id", b["id"])
            .field("json", json.dumps(bdata, ensure_ascii=False))
            .time(meta_ts)
        )

        for fn in range(1, b["floors_count"] + 1):
            fid   = f"floor-{b['id']}-{fn}"
            fdata = {"id": fid, "building_id": b["id"],
                     "floor_number": fn, "status": "Active", "deleted": False}
            # measurement=floors  tags: floor_id, building_id  fields: json
            points.append(
                Point("floors")
                .tag("floor_id",    fid)
                .tag("building_id", b["id"])
                .field("json", json.dumps(fdata, ensure_ascii=False))
                .time(meta_ts)
            )

            for ri in range(rng.randint(3, 5)):
                rid   = f"room-{b['id']}-{fn}-{ri}"
                rdata = {
                    "id": rid, "floor_id": fid, "building_id": b["id"],
                    "room_number": f"{fn}{ri+1:02d}", "type": rng.choice(ROOM_TYPES),
                    "area": round(rng.uniform(20, 80), 1), "comment": "",
                    "status": "Active", "deleted": False,
                }
                # measurement=rooms  tags: room_id, floor_id, building_id  fields: json
                points.append(
                    Point("rooms")
                    .tag("room_id",     rid)
                    .tag("floor_id",    fid)
                    .tag("building_id", b["id"])
                    .field("json", json.dumps(rdata, ensure_ascii=False))
                    .time(meta_ts)
                )

                for mt in METRIC_TYPES:
                    sid     = f"sen-{b['id']}-{fn}-{ri}-{mt[:1]}"
                    sstatus = rng.choice(SENSOR_STATUSES)
                    sdata   = {
                        "id": sid, "room_id": rid, "floor_id": fid,
                        "building_id": b["id"], "metric_type": mt,
                        "model": SENSOR_MODELS[mt], "status": sstatus, "deleted": False,
                    }
                    # measurement=sensors  tags: sensor_id,room_id,floor_id,building_id,metric_type
                    #                      fields: json
                    points.append(
                        Point("sensors")
                        .tag("sensor_id",   sid)
                        .tag("room_id",     rid)
                        .tag("floor_id",    fid)
                        .tag("building_id", b["id"])
                        .tag("metric_type", mt)
                        .field("json", json.dumps(sdata, ensure_ascii=False))
                        .time(meta_ts)
                    )
                    sensors_meta.append(sdata)

                    # climate_readings: every 30 min for 24 h
                    # tags: sensor_id,room_id,floor_id,building_id,metric_type
                    # fields: value (float64), status (string)
                    t = start
                    while t <= now:
                        points.append(
                            Point("climate_readings")
                            .tag("sensor_id",   sid)
                            .tag("room_id",     rid)
                            .tag("floor_id",    fid)
                            .tag("building_id", b["id"])
                            .tag("metric_type", mt)
                            .field("value",  float(_rand_value(mt, t.hour)))
                            .field("status", sstatus)
                            .time(t)
                        )
                        t += timedelta(minutes=30)

                    # sensor_status_history
                    # tags: sensor_id, room_id, building_id
                    # fields: old_status, new_status, reason  (all string)
                    t0 = now - timedelta(days=rng.randint(5, 30))
                    points.append(
                        Point("sensor_status_history")
                        .tag("sensor_id",   sid)
                        .tag("room_id",     rid)
                        .tag("building_id", b["id"])
                        .field("old_status", "Inactive")
                        .field("new_status", "Active")
                        .field("reason",     "Датчик введён в эксплуатацию")
                        .time(t0)
                    )
                    if sstatus in ("Warning", "Error"):
                        t1 = now - timedelta(hours=rng.randint(2, 12))
                        points.append(
                            Point("sensor_status_history")
                            .tag("sensor_id",   sid)
                            .tag("room_id",     rid)
                            .tag("building_id", b["id"])
                            .field("old_status", "Active")
                            .field("new_status", sstatus)
                            .field("reason",     "Автоматическое изменение по порогу")
                            .time(t1)
                        )

    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
        wapi = client.write_api(write_options=SYNCHRONOUS)
        batch = 5_000
        for i in range(0, len(points), batch):
            wapi.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points[i:i + batch])
            log.info("InfluxDB write %d / %d", min(i + batch, len(points)), len(points))

    log.info("InfluxDB seed done: %d points, %d sensors", len(points), len(sensors_meta))
    return sensors_meta


# ════════════════════════════════════════════════════════════════════════════
#  POSTGRESQL  SEED
# ════════════════════════════════════════════════════════════════════════════

_PG_DDL = """
CREATE TABLE IF NOT EXISTS building (
    id           VARCHAR(20) PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    address      VARCHAR(200),
    floors_count INT          CHECK (floors_count >= 1),
    status       VARCHAR(20)  DEFAULT 'Active'
);

CREATE TABLE IF NOT EXISTS floor (
    id           VARCHAR(30) PRIMARY KEY,
    building_id  VARCHAR(20) REFERENCES building(id),
    floor_number INT         NOT NULL CHECK (floor_number >= 1),
    status       VARCHAR(20) DEFAULT 'Active'
);

CREATE TABLE IF NOT EXISTS room (
    id          VARCHAR(40) PRIMARY KEY,
    floor_id    VARCHAR(30) REFERENCES floor(id),
    building_id VARCHAR(20) REFERENCES building(id),
    room_number VARCHAR(10),
    type        VARCHAR(50),
    area        NUMERIC(5,1),
    comment     TEXT        DEFAULT '',
    status      VARCHAR(20) DEFAULT 'Active'
);

CREATE TABLE IF NOT EXISTS sensor (
    id          VARCHAR(50) PRIMARY KEY,
    room_id     VARCHAR(40) REFERENCES room(id),
    floor_id    VARCHAR(30) REFERENCES floor(id),
    building_id VARCHAR(20) REFERENCES building(id),
    metric_type VARCHAR(20),
    model       VARCHAR(50),
    status      VARCHAR(20) DEFAULT 'Active'
);

CREATE TABLE IF NOT EXISTS climate_reading (
    id          BIGSERIAL PRIMARY KEY,
    sensor_id   VARCHAR(50) REFERENCES sensor(id),
    building_id VARCHAR(20),
    metric_type VARCHAR(20),
    value       NUMERIC(7,2),
    status      VARCHAR(20),
    measured_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cr_sensor_time
    ON climate_reading (sensor_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_cr_bldg_metric_time
    ON climate_reading (building_id, metric_type, measured_at DESC);

CREATE TABLE IF NOT EXISTS sensor_status_event (
    id          BIGSERIAL PRIMARY KEY,
    sensor_id   VARCHAR(50) REFERENCES sensor(id),
    room_id     VARCHAR(40),
    building_id VARCHAR(20),
    old_status  VARCHAR(20),
    new_status  VARCHAR(20),
    reason      TEXT,
    occurred_at TIMESTAMPTZ NOT NULL
);
"""


def seed_postgres() -> None:
    log.info("=== Seeding PostgreSQL ===")
    rng = random.Random(42)
    now   = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now - timedelta(hours=24)

    conn = psycopg2.connect(PG_DSN)
    cur  = conn.cursor()
    cur.execute(_PG_DDL)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM building")
    if cur.fetchone()[0] > 0:
        log.info("PostgreSQL already seeded — skipping")
        cur.close(); conn.close()
        return

    readings: list[tuple] = []
    events:   list[tuple] = []

    for b in BUILDINGS:
        cur.execute(
            "INSERT INTO building VALUES (%s,%s,%s,%s,%s)",
            (b["id"], b["name"], b["address"], b["floors_count"], "Active"),
        )
        for fn in range(1, b["floors_count"] + 1):
            fid = f"floor-{b['id']}-{fn}"
            cur.execute(
                "INSERT INTO floor VALUES (%s,%s,%s,%s)",
                (fid, b["id"], fn, "Active"),
            )
            for ri in range(rng.randint(3, 5)):
                rid = f"room-{b['id']}-{fn}-{ri}"
                cur.execute(
                    "INSERT INTO room VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rid, fid, b["id"], f"{fn}{ri+1:02d}",
                     rng.choice(ROOM_TYPES), round(rng.uniform(20, 80), 1), "", "Active"),
                )
                for mt in METRIC_TYPES:
                    sid     = f"sen-{b['id']}-{fn}-{ri}-{mt[:1]}"
                    sstatus = rng.choice(SENSOR_STATUSES)
                    cur.execute(
                        "INSERT INTO sensor VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (sid, rid, fid, b["id"], mt, SENSOR_MODELS[mt], sstatus),
                    )
                    t = start
                    while t <= now:
                        readings.append((sid, b["id"], mt,
                                         _rand_value(mt, t.hour), sstatus, t))
                        t += timedelta(minutes=30)

                    t0 = now - timedelta(days=rng.randint(5, 30))
                    events.append((sid, rid, b["id"],
                                   "Inactive", "Active",
                                   "Датчик введён в эксплуатацию", t0))
                    if sstatus in ("Warning", "Error"):
                        t1 = now - timedelta(hours=rng.randint(2, 12))
                        events.append((sid, rid, b["id"],
                                       "Active", sstatus,
                                       "Автоматическое изменение по порогу", t1))

    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO climate_reading"
        "(sensor_id,building_id,metric_type,value,status,measured_at) VALUES %s",
        readings, page_size=2_000,
    )
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO sensor_status_event"
        "(sensor_id,room_id,building_id,old_status,new_status,reason,occurred_at) VALUES %s",
        events, page_size=2_000,
    )
    conn.commit()
    cur.close(); conn.close()
    log.info("PostgreSQL seed done: %d readings, %d events", len(readings), len(events))


# ════════════════════════════════════════════════════════════════════════════
#  BENCHMARK  QUERIES
# ════════════════════════════════════════════════════════════════════════════

# ── InfluxDB ─────────────────────────────────────────────────────────────────

def _q1_influx(client: InfluxDBClient, _building_id: str) -> float:
    """
    Q1 InfluxDB — список всех корпусов (последняя запись каждой серии).
    Параметр building_id не используется намеренно: запрос возвращает все корпуса,
    50 прогонов измеряют стабильность latency полного сканирования метаданных.
    """
    q = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -36500d)
  |> filter(fn: (r) => r._measurement == "buildings")
  |> filter(fn: (r) => r._field == "json")
  |> group(columns: ["building_id"])
  |> last()
"""
    t0 = time.perf_counter()
    client.query_api().query(q, org=INFLUX_ORG)
    return (time.perf_counter() - t0) * 1000


def _q2_influx(client: InfluxDBClient, building_id: str, metric_type: str) -> float:
    """
    Q2 InfluxDB — почасовой график показаний датчиков одного корпуса за 24 ч.
    Каждый прогон адресован к другому (building_id, metric_type).
    """
    q = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "climate_readings")
  |> filter(fn: (r) => r._field == "value")
  |> filter(fn: (r) => r.building_id == "{building_id}")
  |> filter(fn: (r) => r.metric_type == "{metric_type}")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
"""
    t0 = time.perf_counter()
    client.query_api().query(q, org=INFLUX_ORG)
    return (time.perf_counter() - t0) * 1000


# ── PostgreSQL ────────────────────────────────────────────────────────────────

_SQL_Q1 = """
SELECT
    s.id, s.metric_type, s.model, s.status,
    cr.value        AS last_value,
    cr.measured_at  AS last_measured_at
FROM sensor s
LEFT JOIN LATERAL (
    SELECT value, measured_at
    FROM climate_reading
    WHERE sensor_id = s.id
    ORDER BY measured_at DESC
    LIMIT 1
) cr ON true
WHERE s.building_id = %s
ORDER BY s.id;
"""

_SQL_Q2 = """
SELECT
    DATE_TRUNC('hour', measured_at) AS bucket,
    building_id,
    metric_type,
    ROUND(AVG(value)::numeric, 2)   AS avg_value
FROM climate_reading
WHERE building_id = %s
  AND metric_type = %s
  AND measured_at >= NOW() - INTERVAL '24 hours'
GROUP BY bucket, building_id, metric_type
ORDER BY bucket;
"""


def _q1_pg(conn, building_id: str) -> float:
    """
    Q1 PostgreSQL — датчики корпуса с последним показанием (LATERAL JOIN).
    Каждый прогон — другой building_id.
    """
    t0 = time.perf_counter()
    cur = conn.cursor()
    cur.execute(_SQL_Q1, (building_id,))
    cur.fetchall()
    cur.close()
    return (time.perf_counter() - t0) * 1000


def _q2_pg(conn, building_id: str, metric_type: str) -> float:
    """
    Q2 PostgreSQL — почасовой график за 24 ч (GROUP BY DATE_TRUNC).
    Каждый прогон — другая (building_id, metric_type) пара.
    """
    t0 = time.perf_counter()
    cur = conn.cursor()
    cur.execute(_SQL_Q2, (building_id, metric_type))
    cur.fetchall()
    cur.close()
    return (time.perf_counter() - t0) * 1000


# ════════════════════════════════════════════════════════════════════════════
#  HISTOGRAM
# ════════════════════════════════════════════════════════════════════════════

def save_histogram(times_ms: list[float], title: str, fname: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    arr = np.array(times_ms)

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.hist(arr, bins=15, color="#4A90D9", edgecolor="white", linewidth=0.6)
    ax.set_xlabel("Время выполнения, мс", fontsize=11)
    ax.set_ylabel("Количество запросов", fontsize=11)
    ax.set_title(title, fontsize=12, pad=10)
    ax.grid(axis="y", alpha=0.3)

    stats = (f"n={len(arr)}  "
             f"min={arr.min():.1f}  "
             f"mean={arr.mean():.1f}  "
             f"median={np.median(arr):.1f}  "
             f"p95={np.percentile(arr, 95):.1f}  "
             f"max={arr.max():.1f}  мс")
    ax.text(0.5, 0.97, stats, transform=ax.transAxes,
            ha="center", va="top", fontsize=8.5, color="#555")

    plt.tight_layout()
    path = RESULTS_DIR / fname
    fig.savefig(path, dpi=150)
    plt.close(fig)

    log.info("%-55s  min=%5.1f  mean=%5.1f  p95=%5.1f  max=%5.1f  ms",
             title, arr.min(), arr.mean(), np.percentile(arr, 95), arr.max())


# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════

def run_benchmarks() -> None:
    log.info("=== Running benchmarks  n=%d ===", N_RUNS)

    bids   = [b["id"] for b in BUILDINGS]
    combos = [(b["id"], mt) for b in BUILDINGS for mt in METRIC_TYPES]

    bid_cycle   = itertools.cycle(bids)
    combo_cycle = itertools.cycle(combos)

    # ── InfluxDB ──────────────────────────────────────────────────────────
    t_q1_influx: list[float] = []
    t_q2_influx: list[float] = []

    with InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG) as client:
        for i in range(N_RUNS):
            bid = next(bid_cycle)
            t_q1_influx.append(_q1_influx(client, bid))

        for i in range(N_RUNS):
            bid, mt = next(combo_cycle)
            t_q2_influx.append(_q2_influx(client, bid, mt))

    save_histogram(
        t_q1_influx,
        "Q1 InfluxDB — список корпусов (group + last)",
        "q1_influx.png",
    )
    save_histogram(
        t_q2_influx,
        "Q2 InfluxDB — почасовой график за 24 ч (aggregateWindow)",
        "q2_influx.png",
    )

    # ── PostgreSQL ────────────────────────────────────────────────────────
    t_q1_pg: list[float] = []
    t_q2_pg: list[float] = []

    conn = psycopg2.connect(PG_DSN)
    try:
        for i in range(N_RUNS):
            bid = next(bid_cycle)
            t_q1_pg.append(_q1_pg(conn, bid))

        for i in range(N_RUNS):
            bid, mt = next(combo_cycle)
            t_q2_pg.append(_q2_pg(conn, bid, mt))
    finally:
        conn.close()

    save_histogram(
        t_q1_pg,
        "Q1 PostgreSQL — датчики с последним показанием (LATERAL JOIN)",
        "q1_postgres.png",
    )
    save_histogram(
        t_q2_pg,
        "Q2 PostgreSQL — почасовой график за 24 ч (GROUP BY DATE_TRUNC)",
        "q2_postgres.png",
    )

    log.info("=== Benchmarks complete. Results in %s ===", RESULTS_DIR)


if __name__ == "__main__":
    seed_influx()
    seed_postgres()
    run_benchmarks()
