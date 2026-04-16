"""
Seed the InfluxDB bucket with realistic LETI microclimate data.
Called at every startup:
  - Metadata (buildings / floors / rooms / sensors) is written only once.
  - Climate readings are re-seeded if none exist in the last 25 hours,
    so charts always have fresh data regardless of when the container started.
"""
import random
import math
import logging
from datetime import datetime, timezone, timedelta

from app.influx import (
    query_entities, write_entity, write_entities_batch,
    write_reading, write_status_event, query_latest_readings,
)

logger = logging.getLogger(__name__)


BUILDINGS = [
    {"id": "bldg-1", "name": "Корпус 1 (Главный)",      "address": "ул. Проф. Попова, 5",    "floors_count": 5},
    {"id": "bldg-2", "name": "Корпус 2",                 "address": "Аптекарский пр., 5",     "floors_count": 4},
    {"id": "bldg-3", "name": "Корпус 3",                 "address": "Аптекарский пр., 3",     "floors_count": 4},
    {"id": "bldg-4", "name": "Корпус 4",                 "address": "ул. Проф. Попова, 5",    "floors_count": 3},
    {"id": "bldg-5", "name": "Корпус 5",                 "address": "ул. Проф. Попова, 5",    "floors_count": 3},
    {"id": "bldg-L", "name": "Корпус Л (Лабораторный)", "address": "ул. Проф. Попова, 5",    "floors_count": 3},
    {"id": "bldg-M", "name": "Корпус М (Малый)",        "address": "пр. Медиков, 5",         "floors_count": 2},
    {"id": "bldg-A", "name": "АБК (Административный)",  "address": "пр. Медиков, 5",         "floors_count": 3},
]

ROOM_TYPES = [
    "Аудитория", "Лаборатория", "Кабинет", "Деканат",
    "Библиотека", "Серверная", "Столовая", "Спортзал",
]

METRIC_TYPES  = ["temperature", "humidity", "co2"]
SENSOR_MODELS = {
    "temperature": "SHT31-D",
    "humidity":    "DHT22",
    "co2":         "MH-Z19B",
}
SENSOR_STATUSES = ["Active", "Active", "Active", "Active", "Warning", "Error"]


def _rand_value(metric: str, hour: int) -> float:
    """Simulate realistic values with a daily cycle."""
    if metric == "temperature":
        base = 22.0 + 2 * math.sin(math.pi * hour / 12) + random.uniform(-0.5, 0.5)
        return round(base, 1)
    if metric == "humidity":
        base = 50.0 + 5 * math.sin(math.pi * hour / 12) + random.uniform(-2, 2)
        return round(base, 1)
    if metric == "co2":
        occupied = 1 if 8 <= hour <= 18 else 0
        base = 400 + 300 * occupied + random.uniform(-20, 20)
        return round(base, 1)
    return 0.0


def _readings_are_fresh() -> bool:
    """Return True if there are readings within the last 25 hours."""
    try:
        rows = query_latest_readings()
        if not rows:
            return False
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=25)
        for r in rows:
            if r.get("time"):
                from datetime import datetime as dt
                t = dt.fromisoformat(r["time"].replace("Z", "+00:00"))
                if t > cutoff:
                    return True
        return False
    except Exception as e:
        logger.warning("Could not check reading freshness: %s", e)
        return False


def _seed_readings(all_sensors: list) -> None:
    """Write 24 h of synthetic climate readings (every 30 min) ending right now."""
    logger.info("Generating synthetic time-series (24 h, 1 pt / 30 min) …")
    now   = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = now - timedelta(hours=24)
    points = []

    for sdata, floor_id, building_id in all_sensors:
        t = start
        while t <= now:
            val = _rand_value(sdata["metric_type"], t.hour)
            pt  = write_reading(
                sdata["id"], sdata["room_id"], floor_id, building_id,
                sdata["metric_type"], val, sdata["status"], t,
            )
            points.append(pt)
            t += timedelta(minutes=30)

    write_entities_batch(points)
    logger.info("Wrote %d climate readings.", len(points))


def seed_if_empty():
    existing_buildings = query_entities("buildings", "building_id")

    # Шаг 1: засеять метаданные один раз
    if existing_buildings:
        logger.info(
            "Metadata already present (%d buildings). Skipping metadata seed.",
            len(existing_buildings),
        )
        all_sensors = _load_existing_sensors()
    else:
        logger.info("Seeding InfluxDB with LETI metadata …")
        all_sensors = _seed_metadata()

    # шаг 2: (пере)засеять показания, если устарели или отсутствуют
    if _readings_are_fresh():
        logger.info("Readings are fresh — skipping readings seed.")
    else:
        logger.info("Readings are stale or absent — re-seeding last 24 h …")
        _seed_readings(all_sensors)

    logger.info("Seed/refresh complete. Sensors in memory: %d", len(all_sensors))


def _load_existing_sensors() -> list:
    """Load sensor metadata from InfluxDB to rebuild all_sensors list."""
    sensors = query_entities("sensors", "sensor_id")
    result = []
    for s in sensors:
        result.append((s, s.get("floor_id", ""), s.get("building_id", "")))
    return result


def _seed_metadata() -> list:
    """Write buildings / floors / rooms / sensors. Returns all_sensors list."""
    rng = random.Random(42)
    all_sensors = []

    for b in BUILDINGS:
        bdata = {**b, "status": "Active", "deleted": False}
        write_entity("buildings", "building_id", b["id"], bdata)

        for fn in range(1, b["floors_count"] + 1):
            floor_id = f"floor-{b['id']}-{fn}"
            fdata = {
                "id":           floor_id,
                "building_id":  b["id"],
                "floor_number": fn,
                "status":       "Active",
                "deleted":      False,
            }
            write_entity("floors", "floor_id", floor_id, fdata,
                         extra_tags={"building_id": b["id"]})

            n_rooms = rng.randint(3, 5)
            for ri in range(n_rooms):
                room_num = f"{fn}{ri+1:02d}"
                room_id  = f"room-{b['id']}-{fn}-{ri}"
                rtype    = rng.choice(ROOM_TYPES)
                rdata = {
                    "id":          room_id,
                    "floor_id":    floor_id,
                    "building_id": b["id"],
                    "room_number": room_num,
                    "type":        rtype,
                    "area":        round(rng.uniform(20, 80), 1),
                    "comment":     "",
                    "status":      "Active",
                    "deleted":     False,
                }
                write_entity("rooms", "room_id", room_id, rdata,
                             extra_tags={"floor_id": floor_id, "building_id": b["id"]})

                for mt in METRIC_TYPES:
                    sensor_id = f"sen-{b['id']}-{fn}-{ri}-{mt[:1]}"
                    sstatus   = rng.choice(SENSOR_STATUSES)
                    sdata = {
                        "id":          sensor_id,
                        "room_id":     room_id,
                        "floor_id":    floor_id,
                        "building_id": b["id"],
                        "metric_type": mt,
                        "model":       SENSOR_MODELS[mt],
                        "status":      sstatus,
                        "deleted":     False,
                    }
                    write_entity("sensors", "sensor_id", sensor_id, sdata,
                                 extra_tags={"room_id": room_id, "floor_id": floor_id,
                                             "building_id": b["id"], "metric_type": mt})
                    all_sensors.append((sdata, floor_id, b["id"]))

    logger.info("Metadata written: buildings=%d", len(BUILDINGS))

    rng2 = random.Random(42)
    now  = datetime.now(timezone.utc)
    history_pts = []
    for sdata, floor_id, building_id in all_sensors:
        if sdata["status"] in ("Warning", "Error"):
            t1 = now - timedelta(hours=rng2.randint(2, 12))
            history_pts.append(write_status_event(
                sdata["id"], sdata["room_id"], building_id,
                "Active", sdata["status"], "Автоматическое изменение по порогу", t1,
            ))
        t0 = now - timedelta(days=rng2.randint(5, 30))
        history_pts.append(write_status_event(
            sdata["id"], sdata["room_id"], building_id,
            "Inactive", "Active", "Датчик введён в эксплуатацию", t0,
        ))
    write_entities_batch(history_pts)
    logger.info("History events written: %d", len(history_pts))

    return all_sensors