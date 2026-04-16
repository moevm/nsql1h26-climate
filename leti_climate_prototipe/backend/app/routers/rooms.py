import uuid
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
def list_rooms(floor_id: Optional[str] = None, building_id: Optional[str] = None,
               room_number: Optional[str] = None, type: Optional[str] = None,
               status: Optional[str] = None, _=Depends(get_current_user)):
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
    items.sort(key=lambda x: (x.get("building_id",""), x.get("floor_id",""), x.get("room_number","")))
    return items


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
    data = {**body.model_dump(), "id": rid, "deleted": False}
    write_entity("rooms", "room_id", rid, data,
                 extra_tags={"floor_id": body.floor_id, "building_id": body.building_id})
    return data


@router.put("/{rid}")
def update_room(rid: str, body: RoomIn, _=Depends(require_admin)):
    rows = query_entities("rooms", "room_id", {"room_id": rid})
    if not rows:
        raise HTTPException(404, "Помещение не найдено")
    data = {**rows[0], **body.model_dump()}
    write_entity("rooms", "room_id", rid, data,
                 extra_tags={"floor_id": body.floor_id, "building_id": body.building_id})
    return data


@router.delete("/{rid}")
def delete_room(rid: str, _=Depends(require_admin)):
    soft_delete("rooms", "room_id", rid)
    return {"status": "deleted"}