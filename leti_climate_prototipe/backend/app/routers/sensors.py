import math
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from app.influx import (
    write_entity, query_entities, soft_delete,
    query_latest_readings, query_sensor_history, write_status_event, write_entities_batch
)
from app.auth import get_current_user, require_admin

router = APIRouter()


class SensorIn(BaseModel):
    room_id: str
    floor_id: str
    building_id: str
    metric_type: str
    model: str
    status: str = "Active"

    @field_validator("metric_type")
    @classmethod
    def metric_type_valid(cls, v):
        allowed = {"temperature", "humidity", "co2"}
        if v not in allowed:
            raise ValueError(f"Тип метрики должен быть одним из: {', '.join(sorted(allowed))}")
        return v


class StatusUpdate(BaseModel):
    status: str
    reason: str = ""


@router.get("")
def list_sensors(
    room_id: Optional[str] = None, building_id: Optional[str] = None,
    floor_id: Optional[str] = None, metric_type: Optional[str] = None,
    status: Optional[str] = None, sensor_id: Optional[str] = None,
    model: Optional[str] = None,
    created_from: Optional[str] = None, created_to: Optional[str] = None,
    updated_from: Optional[str] = None, updated_to: Optional[str] = None,
    page: int = 1, page_size: int = 25,
    _=Depends(get_current_user)
):
    tf = {}
    if room_id:     tf["room_id"]     = room_id
    if building_id: tf["building_id"] = building_id
    if floor_id:    tf["floor_id"]    = floor_id
    if metric_type: tf["metric_type"] = metric_type
    sensors = query_entities("sensors", "sensor_id", tf or None)

    if status:
        sensors = [s for s in sensors if s.get("status", "").lower() == status.lower()]
    if sensor_id:
        sensors = [s for s in sensors if sensor_id.lower() in s.get("id", "").lower()]
    if model:
        sensors = [s for s in sensors if model.lower() in s.get("model", "").lower()]
    if created_from:
        sensors = [s for s in sensors if s.get("created_at", "") >= created_from]
    if created_to:
        to_val = (created_to + ":59") if "T" in created_to else (created_to + "T23:59:59")
        sensors = [s for s in sensors if s.get("created_at", "") <= to_val]
    if updated_from:
        sensors = [s for s in sensors if s.get("updated_at", "") >= updated_from]
    if updated_to:
        to_val = (updated_to + ":59") if "T" in updated_to else (updated_to + "T23:59:59")
        sensors = [s for s in sensors if s.get("updated_at", "") <= to_val]

    readings = query_latest_readings(tf or None)
    latest = {(r["sensor_id"], r["metric_type"]): r["value"] for r in readings}
    for s in sensors:
        s["last_value"] = latest.get((s["id"], s["metric_type"]))

    sensors.sort(key=lambda x: x.get("id", ""))
    total = len(sensors)
    if page_size > 0:
        start = (page - 1) * page_size
        sensors = sensors[start:start + page_size]
    pages = math.ceil(total / page_size) if page_size > 0 and total > 0 else 1
    return {"items": sensors, "total": total, "page": page, "pages": pages}


@router.get("/{sid}")
def get_sensor(sid: str, _=Depends(get_current_user)):
    rows = query_entities("sensors", "sensor_id", {"sensor_id": sid})
    if not rows:
        raise HTTPException(404, "Датчик не найден")
    s = rows[0]
    readings = query_latest_readings({"sensor_id": sid})
    s["last_value"] = readings[0]["value"] if readings else None
    return s


@router.post("")
def create_sensor(body: SensorIn, _=Depends(require_admin)):
    sid = "sen-" + str(uuid.uuid4())[:8]
    now = datetime.now(timezone.utc).isoformat()
    data = {**body.model_dump(), "id": sid, "deleted": False,
            "created_at": now, "updated_at": now}
    write_entity("sensors", "sensor_id", sid, data,
                 extra_tags={k: getattr(body, k) for k in
                             ("room_id", "floor_id", "building_id", "metric_type")})
    pts = [write_status_event(sid, body.room_id, body.building_id,
                              "Inactive", body.status, "Датчик добавлен",
                              datetime.now(timezone.utc))]
    write_entities_batch(pts)
    return data


@router.put("/{sid}")
def update_sensor(sid: str, body: SensorIn, _=Depends(require_admin)):
    rows = query_entities("sensors", "sensor_id", {"sensor_id": sid})
    if not rows:
        raise HTTPException(404, "Датчик не найден")
    old = rows[0]
    now = datetime.now(timezone.utc).isoformat()
    data = {**old, **body.model_dump(), "updated_at": now}
    if "created_at" not in data:
        data["created_at"] = now
    write_entity("sensors", "sensor_id", sid, data,
                 extra_tags={k: getattr(body, k) for k in
                             ("room_id", "floor_id", "building_id", "metric_type")})
    if old.get("status") != body.status:
        pts = [write_status_event(sid, body.room_id, body.building_id,
                                  old["status"], body.status, "Ручное изменение",
                                  datetime.now(timezone.utc))]
        write_entities_batch(pts)
    return data


@router.patch("/{sid}/status")
def update_sensor_status(sid: str, body: StatusUpdate, _=Depends(require_admin)):
    rows = query_entities("sensors", "sensor_id", {"sensor_id": sid})
    if not rows:
        raise HTTPException(404, "Датчик не найден")
    old = rows[0]
    allowed = {"Active", "Inactive", "Warning", "Error"}
    if body.status not in allowed:
        raise HTTPException(422, f"Статус должен быть одним из: {', '.join(allowed)}")
    now = datetime.now(timezone.utc).isoformat()
    data = {**old, "status": body.status, "updated_at": now}
    write_entity("sensors", "sensor_id", sid, data,
                 extra_tags={k: old[k] for k in
                             ("room_id", "floor_id", "building_id", "metric_type")})
    if old.get("status") != body.status:
        pts = [write_status_event(sid, old["room_id"], old["building_id"],
                                  old.get("status", ""), body.status,
                                  body.reason or "Ручное изменение статуса",
                                  datetime.now(timezone.utc))]
        write_entities_batch(pts)
    return {**data, "previous_status": old.get("status")}


@router.delete("/{sid}")
def delete_sensor(sid: str, _=Depends(require_admin)):
    soft_delete("sensors", "sensor_id", sid)
    return {"status": "deleted"}


@router.get("/{sid}/history")
def sensor_history(sid: str, start: str = "-30d", _=Depends(get_current_user)):
    return query_sensor_history(sid, start)
