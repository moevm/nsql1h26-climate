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
def list_floors(building_id: Optional[str] = None, status: Optional[str] = None,
                _=Depends(get_current_user)):
    tf = {"building_id": building_id} if building_id else None
    items = query_entities("floors", "floor_id", tf)
    if status:
        items = [i for i in items if i.get("status", "").lower() == status.lower()]
    items.sort(key=lambda x: (x.get("building_id", ""), x.get("floor_number", 0)))
    return items


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
