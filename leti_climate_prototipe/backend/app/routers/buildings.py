import math
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from app.influx import write_entity, query_entities, soft_delete
from app.auth import get_current_user, require_admin

router = APIRouter()


class BuildingIn(BaseModel):
    name: str
    address: str
    floors_count: int
    status: str = "Active"

    @field_validator("floors_count")
    @classmethod
    def floors_positive(cls, v):
        if v < 1:
            raise ValueError("Количество этажей должно быть не менее 1")
        return v


@router.get("")
def list_buildings(
    name: Optional[str] = None, address: Optional[str] = None,
    status: Optional[str] = None,
    floors_min: Optional[int] = None, floors_max: Optional[int] = None,
    created_from: Optional[str] = None, created_to: Optional[str] = None,
    updated_from: Optional[str] = None, updated_to: Optional[str] = None,
    page: int = 1, page_size: int = 25,
    _=Depends(get_current_user)
):
    items = query_entities("buildings", "building_id")
    if name:
        items = [i for i in items if name.lower() in i.get("name", "").lower()]
    if address:
        items = [i for i in items if address.lower() in i.get("address", "").lower()]
    if status:
        items = [i for i in items if i.get("status", "").lower() == status.lower()]
    if floors_min is not None:
        items = [i for i in items if i.get("floors_count", 0) >= floors_min]
    if floors_max is not None:
        items = [i for i in items if i.get("floors_count", 0) <= floors_max]
    if created_from:
        items = [i for i in items if i.get("created_at", "") >= created_from]
    if created_to:
        items = [i for i in items if i.get("created_at", "") <= created_to + "T23:59:59Z"]
    if updated_from:
        items = [i for i in items if i.get("updated_at", "") >= updated_from]
    if updated_to:
        items = [i for i in items if i.get("updated_at", "") <= updated_to + "T23:59:59Z"]
    items.sort(key=lambda x: x.get("name", ""))
    total = len(items)
    if page_size > 0:
        start = (page - 1) * page_size
        items = items[start:start + page_size]
    pages = math.ceil(total / page_size) if page_size > 0 and total > 0 else 1
    return {"items": items, "total": total, "page": page, "pages": pages}


@router.get("/{bid}")
def get_building(bid: str, _=Depends(get_current_user)):
    rows = query_entities("buildings", "building_id", {"building_id": bid})
    if not rows:
        raise HTTPException(404, "Корпус не найден")
    return rows[0]


@router.post("")
def create_building(body: BuildingIn, _=Depends(require_admin)):
    bid = "bldg-" + str(uuid.uuid4())[:6]
    now = datetime.now(timezone.utc).isoformat()
    data = {**body.model_dump(), "id": bid, "deleted": False,
            "created_at": now, "updated_at": now}
    write_entity("buildings", "building_id", bid, data)
    return data


@router.put("/{bid}")
def update_building(bid: str, body: BuildingIn, _=Depends(require_admin)):
    rows = query_entities("buildings", "building_id", {"building_id": bid})
    if not rows:
        raise HTTPException(404, "Корпус не найден")
    now = datetime.now(timezone.utc).isoformat()
    data = {**rows[0], **body.model_dump(), "updated_at": now}
    if "created_at" not in data:
        data["created_at"] = now
    write_entity("buildings", "building_id", bid, data)
    return data


@router.delete("/{bid}")
def delete_building(bid: str, _=Depends(require_admin)):
    soft_delete("buildings", "building_id", bid)
    return {"status": "deleted"}


@router.get("/{bid}/floors")
def get_floors(bid: str, _=Depends(get_current_user)):
    items = query_entities("floors", "floor_id", {"building_id": bid})
    items.sort(key=lambda x: x.get("floor_number", 0))
    return items
