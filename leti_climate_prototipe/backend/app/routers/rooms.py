import math
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.influx import write_entity, query_entities, soft_delete, query_latest_readings
from app.auth import get_current_user, require_admin

router = APIRouter()


class RoomIn(BaseModel):
    floor_id: str
    building_id: str
    room_number: str
    type: str
    area: float
    comment: str = ""
    status: str = "Active"


@router.get("")
def list_rooms(
    floor_id: Optional[str] = None, building_id: Optional[str] = None,
    room_number: Optional[str] = None, type: Optional[str] = None,
    status: Optional[str] = None,
    area_min: Optional[float] = None, area_max: Optional[float] = None,
    created_from: Optional[str] = None, created_to: Optional[str] = None,
    updated_from: Optional[str] = None, updated_to: Optional[str] = None,
    temp_min: Optional[float] = None, temp_max: Optional[float] = None,
    hum_min: Optional[float] = None, hum_max: Optional[float] = None,
    co2_min: Optional[float] = None, co2_max: Optional[float] = None,
    page: int = 1, page_size: int = 25,
    _=Depends(get_current_user)
):
    tf = {}
    if floor_id:    tf["floor_id"]    = floor_id
    if building_id: tf["building_id"] = building_id
    items = query_entities("rooms", "room_id", tf or None)
    if room_number:
        items = [i for i in items if room_number.lower() in i.get("room_number", "").lower()]
    if type:
        items = [i for i in items if type.lower() in i.get("type", "").lower()]
    if status:
        items = [i for i in items if i.get("status", "").lower() == status.lower()]
    if area_min is not None:
        items = [i for i in items if i.get("area", 0) >= area_min]
    if area_max is not None:
        items = [i for i in items if i.get("area", 0) <= area_max]
    if created_from:
        items = [i for i in items if i.get("created_at", "") >= created_from]
    if created_to:
        to_val = (created_to + ":59") if "T" in created_to else (created_to + "T23:59:59")
        items = [i for i in items if i.get("created_at", "") <= to_val]
    if updated_from:
        items = [i for i in items if i.get("updated_at", "") >= updated_from]
    if updated_to:
        to_val = (updated_to + ":59") if "T" in updated_to else (updated_to + "T23:59:59")
        items = [i for i in items if i.get("updated_at", "") <= to_val]

    needs_metrics = any(x is not None for x in [temp_min, temp_max, hum_min, hum_max, co2_min, co2_max])
    if needs_metrics:
        reads = query_latest_readings(tf or None)
        room_metrics: dict = {}
        for r in reads:
            rid = r.get("room_id")
            mt = r.get("metric_type")
            v = r.get("value")
            if rid and mt and v is not None:
                room_metrics.setdefault(rid, {})[mt] = float(v)

        def passes_metric(item):
            m = room_metrics.get(item.get("id", ""), {})
            t, h, c = m.get("temperature"), m.get("humidity"), m.get("co2")
            if temp_min is not None and (t is None or t < temp_min): return False
            if temp_max is not None and (t is None or t > temp_max): return False
            if hum_min is not None and (h is None or h < hum_min): return False
            if hum_max is not None and (h is None or h > hum_max): return False
            if co2_min is not None and (c is None or c < co2_min): return False
            if co2_max is not None and (c is None or c > co2_max): return False
            return True

        items = [i for i in items if passes_metric(i)]

    items.sort(key=lambda x: (x.get("building_id", ""), x.get("floor_id", ""), x.get("room_number", "")))
    total = len(items)
    if page_size > 0:
        start = (page - 1) * page_size
        items = items[start:start + page_size]
    pages = math.ceil(total / page_size) if page_size > 0 and total > 0 else 1
    return {"items": items, "total": total, "page": page, "pages": pages}


@router.get("/{rid}")
def get_room(rid: str, _=Depends(get_current_user)):
    rows = query_entities("rooms", "room_id", {"room_id": rid})
    if not rows:
        raise HTTPException(404, "Помещение не найдено")
    room = rows[0]
    readings = query_latest_readings({"room_id": rid})
    metrics = {}
    for r in readings:
        metrics[r["metric_type"]] = {"value": r["value"], "time": r["time"]}
    room["metrics"] = metrics
    return room


@router.post("")
def create_room(body: RoomIn, _=Depends(require_admin)):
    rid = "room-" + str(uuid.uuid4())[:6]
    now = datetime.now(timezone.utc).isoformat()
    data = {**body.model_dump(), "id": rid, "deleted": False,
            "created_at": now, "updated_at": now}
    write_entity("rooms", "room_id", rid, data,
                 extra_tags={"floor_id": body.floor_id, "building_id": body.building_id})
    return data


@router.put("/{rid}")
def update_room(rid: str, body: RoomIn, _=Depends(require_admin)):
    rows = query_entities("rooms", "room_id", {"room_id": rid})
    if not rows:
        raise HTTPException(404, "Помещение не найдено")
    now = datetime.now(timezone.utc).isoformat()
    data = {**rows[0], **body.model_dump(), "updated_at": now}
    if "created_at" not in data:
        data["created_at"] = now
    write_entity("rooms", "room_id", rid, data,
                 extra_tags={"floor_id": body.floor_id, "building_id": body.building_id})
    return data


@router.delete("/{rid}")
def delete_room(rid: str, _=Depends(require_admin)):
    soft_delete("rooms", "room_id", rid)
    return {"status": "deleted"}
