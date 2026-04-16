import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from app.influx import query_entities, write_entity, query_latest_readings
from app.auth import get_current_user, require_admin

router = APIRouter()

MEASUREMENTS = [
    ("buildings", "building_id", []),
    ("floors",    "floor_id",    ["building_id"]),
    ("rooms",     "room_id",     ["floor_id", "building_id"]),
    ("sensors",   "sensor_id",   ["room_id", "floor_id", "building_id", "metric_type"]),
]


@router.get("/export")
def export_all(_=Depends(get_current_user)):
    dump = {}
    for meas, id_tag, _ in MEASUREMENTS:
        dump[meas] = query_entities(meas, id_tag)
    dump["readings_latest"] = query_latest_readings()
    dump["exported_at"] = datetime.now(timezone.utc).isoformat()
    return JSONResponse(content=dump, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="leti_climate_export.json"'})


@router.post("/import")
async def import_all(file: UploadFile = File(...), _=Depends(require_admin)):
    try:
        raw = await file.read()
        data = json.loads(raw)
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения файла: {e}")

    counts = {}
    for meas, id_tag, extra_tag_keys in MEASUREMENTS:
        items = data.get(meas, [])
        for item in items:
            item["deleted"] = False
            extra = {k: item[k] for k in extra_tag_keys if k in item}
            write_entity(meas, id_tag, item[id_tag if id_tag in item else "id"], item,
                         extra_tags=extra)
        counts[meas] = len(items)

    return {"status": "imported", "counts": counts}