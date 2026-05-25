import math
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from app.influx import write_entity, query_entities, soft_delete
from app.auth import get_current_user, require_admin

router = APIRouter()


class FloorIn(BaseModel):
    building_id: str
    floor_number: int
    status: str = "Active"

    @field_validator("floor_number")
    @classmethod
    def floor_positive(cls, v):
        if v < 1:
            raise ValueError("Номер этажа должен быть не менее 1")
        return v


@router.get("")
def list_floors(
    building_id: Optional[str] = None, status: Optional[str] = None,
    floor_min: Optional[int] = None, floor_max: Optional[int] = None,
    created_from: Optional[str] = None, created_to: Optional[str] = None,
    updated_from: Optional[str] = None, updated_to: Optional[str] = None,
    temp_min: Optional[float] = None, temp_max: Optional[float] = None,
    hum_min: Optional[float] = None, hum_max: Optional[float] = None,
    co2_min: Optional[float] = None, co2_max: Optional[float] = None,
    page: int = 1, page_size: int = 25,
    _=Depends(get_current_user)
):
    tf = {"building_id": building_id} if building_id else None
    items = query_entities("floors", "floor_id", tf)
    if status:
        items = [i for i in items if i.get("status", "").lower() == status.lower()]
    if floor_min is not None:
        items = [i for i in items if i.get("floor_number", 0) >= floor_min]
    if floor_max is not None:
        items = [i for i in items if i.get("floor_number", 0) <= floor_max]
    if created_from:
        items = [i for i in items if i.get("created_at", "") >= created_from]
    if created_to:
        items = [i for i in items if i.get("created_at", "") <= created_to + "T23:59:59Z"]
    if updated_from:
        items = [i for i in items if i.get("updated_at", "") >= updated_from]
    if updated_to:
        items = [i for i in items if i.get("updated_at", "") <= updated_to + "T23:59:59Z"]

    needs_metrics = any(x is not None for x in [temp_min, temp_max, hum_min, hum_max, co2_min, co2_max])
    if needs_metrics:
        from app.influx import query_latest_readings
        readings = query_latest_readings(None)
        floor_sums: dict = {}
        floor_cnts: dict = {}
        for r in readings:
            fid = r.get("floor_id")
            mt = r.get("metric_type")
            v = r.get("value")
            if not fid or not mt or v is None:
                continue
            floor_sums.setdefault(fid, {}).setdefault(mt, 0.0)
            floor_cnts.setdefault(fid, {}).setdefault(mt, 0)
            floor_sums[fid][mt] += float(v)
            floor_cnts[fid][mt] += 1
        floor_avgs = {
            fid: {mt: floor_sums[fid][mt] / floor_cnts[fid][mt] for mt in floor_sums[fid]}
            for fid in floor_sums
        }

        def passes_metric(item):
            fid = item.get("id", "")
            avgs = floor_avgs.get(fid, {})
            t = avgs.get("temperature")
            h = avgs.get("humidity")
            c = avgs.get("co2")
            if temp_min is not None and (t is None or t < temp_min):
                return False
            if temp_max is not None and (t is None or t > temp_max):
                return False
            if hum_min is not None and (h is None or h < hum_min):
                return False
            if hum_max is not None and (h is None or h > hum_max):
                return False
            if co2_min is not None and (c is None or c < co2_min):
                return False
            if co2_max is not None and (c is None or c > co2_max):
                return False
            return True

        items = [i for i in items if passes_metric(i)]

    items.sort(key=lambda x: (x.get("building_id", ""), x.get("floor_number", 0)))
    total = len(items)
    if page_size > 0:
        start = (page - 1) * page_size
        items = items[start:start + page_size]
    pages = math.ceil(total / page_size) if page_size > 0 and total > 0 else 1
    return {"items": items, "total": total, "page": page, "pages": pages}


@router.get("/{fid}")
def get_floor(fid: str, _=Depends(get_current_user)):
    rows = query_entities("floors", "floor_id", {"floor_id": fid})
    if not rows:
        raise HTTPException(404, "Этаж не найден")
    return rows[0]


@router.post("")
def create_floor(body: FloorIn, _=Depends(require_admin)):
    fid = "floor-" + str(uuid.uuid4())[:6]
    now = datetime.now(timezone.utc).isoformat()
    data = {**body.model_dump(), "id": fid, "deleted": False,
            "created_at": now, "updated_at": now}
    write_entity("floors", "floor_id", fid, data,
                 extra_tags={"building_id": body.building_id})
    return data


@router.put("/{fid}")
def update_floor(fid: str, body: FloorIn, _=Depends(require_admin)):
    rows = query_entities("floors", "floor_id", {"floor_id": fid})
    if not rows:
        raise HTTPException(404, "Этаж не найден")
    now = datetime.now(timezone.utc).isoformat()
    data = {**rows[0], **body.model_dump(), "updated_at": now}
    if "created_at" not in data:
        data["created_at"] = now
    write_entity("floors", "floor_id", fid, data,
                 extra_tags={"building_id": body.building_id})
    return data


@router.delete("/{fid}")
def delete_floor(fid: str, _=Depends(require_admin)):
    soft_delete("floors", "floor_id", fid)
    return {"status": "deleted"}


@router.get("/{fid}/rooms")
def get_rooms(fid: str, _=Depends(get_current_user)):
    items = query_entities("rooms", "room_id", {"floor_id": fid})
    items.sort(key=lambda x: x.get("room_number", ""))
    return items
