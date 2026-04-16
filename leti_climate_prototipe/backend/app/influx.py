import json
import os
import logging
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)

INFLUX_URL    = os.getenv("INFLUX_URL",    "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN",  "leti-super-secret-token-2026")
INFLUX_ORG    = os.getenv("INFLUX_ORG",    "leti")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "climate")


def get_client():
    return InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)


def ping():
    try:
        with get_client() as c:
            return c.ping()
    except Exception:
        return False


def write_entity(measurement, id_tag, id_value, data, extra_tags=None, ts=None):
    ts = ts or datetime.now(timezone.utc)
    with get_client() as c:
        write_api = c.write_api(write_options=SYNCHRONOUS)
        pt = Point(measurement).tag(id_tag, id_value)
        for k, v in (extra_tags or {}).items():
            pt = pt.tag(k, str(v))
        pt = pt.field("json", json.dumps(data, ensure_ascii=False))
        pt = pt.time(ts)
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=pt)


def write_entities_batch(points):
    with get_client() as c:
        write_api = c.write_api(write_options=SYNCHRONOUS)
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)


def _build_filter_clauses(tag_filters):
    return "\n  ".join(
        f'|> filter(fn: (r) => r.{k} == "{v}")'
        for k, v in (tag_filters or {}).items()
    )


def query_entities(measurement, id_tag, tag_filters=None):
    tag_part = _build_filter_clauses(tag_filters)
    query = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -36500d)
  |> filter(fn: (r) => r._measurement == "{measurement}")
  |> filter(fn: (r) => r._field == "json")
  {tag_part}
  |> group(columns: ["{id_tag}"])
  |> last()
"""
    with get_client() as c:
        tables = c.query_api().query(query, org=INFLUX_ORG)
    result = []
    for table in tables:
        for rec in table.records:
            try:
                d = json.loads(rec.get_value())
                if not d.get("deleted"):
                    result.append(d)
            except Exception as e:
                logger.warning("parse error in %s: %s", measurement, e)
    return result


def soft_delete(measurement, id_tag, id_value, extra_tags=None):
    rows = query_entities(measurement, id_tag, {id_tag: id_value})
    if rows:
        d = rows[0]
        d["deleted"] = True
        write_entity(measurement, id_tag, id_value, d, extra_tags=extra_tags)



def write_reading(sensor_id, room_id, floor_id, building_id, metric_type, value, status, ts):
    return (Point("climate_readings")
            .tag("sensor_id",   sensor_id)
            .tag("room_id",     room_id)
            .tag("floor_id",    floor_id)
            .tag("building_id", building_id)
            .tag("metric_type", metric_type)
            .field("value",  float(value))
            .field("status", status)
            .time(ts))


def query_latest_readings(tag_filters=None):
    tag_part = _build_filter_clauses(tag_filters)
    query = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -36500d)
  |> filter(fn: (r) => r._measurement == "climate_readings")
  |> filter(fn: (r) => r._field == "value")
  {tag_part}
  |> group(columns: ["sensor_id", "metric_type"])
  |> last()
"""
    with get_client() as c:
        tables = c.query_api().query(query, org=INFLUX_ORG)
    rows = []
    for table in tables:
        for rec in table.records:
            rows.append({
                "sensor_id":   rec.values.get("sensor_id"),
                "room_id":     rec.values.get("room_id"),
                "floor_id":    rec.values.get("floor_id"),
                "building_id": rec.values.get("building_id"),
                "metric_type": rec.values.get("metric_type"),
                "value":       rec.get_value(),
                "time":        rec.get_time().isoformat() if rec.get_time() else None,
            })
    return rows


def _get_building_ids_from_metadata():
    """Return list of active building IDs from the buildings metadata measurement.
    Much more reliable than querying the time-series for distinct values."""
    buildings = query_entities("buildings", "building_id")
    return [b["id"] for b in buildings]


def query_readings_range(start, metric_type=None, building_id=None,
                         floor_id=None, room_id=None, win="1h"):
    """
    Окно усреднения сгруппировано по (building_id, metric_type).
    Запросы выполняются по каждому корпусу отдельно, чтобы building_id не терялся после агрегации.
    Идентификаторы зданий берутся из метаданных, а не из диапазона временного ряда.
    """
    extra = ""
    if metric_type:
        extra += f'\n  |> filter(fn: (r) => r.metric_type == "{metric_type}")'
    if floor_id:
        extra += f'\n  |> filter(fn: (r) => r.floor_id == "{floor_id}")'
    if room_id:
        extra += f'\n  |> filter(fn: (r) => r.room_id == "{room_id}")'

    if building_id:
        bids = [building_id]
    else:
        bids = _get_building_ids_from_metadata()

    if not bids:
        logger.warning("query_readings_range: no buildings found in metadata")
        return []

    rows = []
    with get_client() as c:
        qapi = c.query_api()
        for bid in bids:
            q = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {start})
  |> filter(fn: (r) => r._measurement == "climate_readings")
  |> filter(fn: (r) => r._field == "value")
  |> filter(fn: (r) => r.building_id == "{bid}")
  {extra}
  |> aggregateWindow(every: {win}, fn: mean, createEmpty: false)
"""
            tbls = qapi.query(q, org=INFLUX_ORG)
            for table in tbls:
                for rec in table.records:
                    t = rec.get_time()
                    v = rec.get_value()
                    if t is None or v is None:
                        continue
                    mt = rec.values.get("metric_type") or metric_type or "unknown"
                    rows.append({
                        "time":        t.isoformat(),
                        "value":       round(float(v), 2),
                        "metric_type": mt,
                        "building_id": bid,
                    })
    rows.sort(key=lambda r: r["time"])
    return rows


def write_status_event(sensor_id, room_id, building_id,
                       old_status, new_status, reason, ts):
    return (Point("sensor_status_history")
            .tag("sensor_id",   sensor_id)
            .tag("room_id",     room_id)
            .tag("building_id", building_id)
            .field("old_status", old_status)
            .field("new_status", new_status)
            .field("reason",     reason)
            .time(ts))


def query_sensor_history(sensor_id, start="-30d"):
    query = f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: {start})
  |> filter(fn: (r) => r._measurement == "sensor_status_history")
  |> filter(fn: (r) => r.sensor_id == "{sensor_id}")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> sort(columns: ["_time"], desc: true)
"""
    with get_client() as c:
        tables = c.query_api().query(query, org=INFLUX_ORG)
    rows = []
    for table in tables:
        for rec in table.records:
            rows.append({
                "time":       rec.get_time().isoformat() if rec.get_time() else None,
                "old_status": rec.values.get("old_status"),
                "new_status": rec.values.get("new_status"),
                "reason":     rec.values.get("reason"),
                "sensor_id":  sensor_id,
            })
    return rows


def query_dashboard_stats():
    """Average per building per metric, computed from latest readings per sensor.
    Uses query_latest_readings() (proven to work) and aggregates in Python."""
    rows = query_latest_readings()
    sums: dict = {}
    cnts: dict = {}
    for r in rows:
        bid = r.get("building_id") or "unknown"
        mt  = r.get("metric_type") or "unknown"
        v   = r.get("value")
        if v is None:
            continue
        sums.setdefault(bid, {}).setdefault(mt, 0)
        cnts.setdefault(bid, {}).setdefault(mt, 0)
        sums[bid][mt] += float(v)
        cnts[bid][mt] += 1
    return {
        bid: {
            mt: round(sums[bid][mt] / cnts[bid][mt], 2)
            for mt in sums[bid]
        }
        for bid in sums
    }