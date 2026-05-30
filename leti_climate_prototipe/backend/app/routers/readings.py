from typing import Optional
from fastapi import APIRouter, Depends
from app.influx import query_latest_readings, query_readings_range, query_dashboard_stats
from app.auth import get_current_user

router = APIRouter()


@router.get("/latest")
def latest_readings(sensor_id: Optional[str] = None, room_id: Optional[str] = None,
                    building_id: Optional[str] = None, metric_type: Optional[str] = None,
                    _=Depends(get_current_user)):
    tf = {}
    if sensor_id:   tf["sensor_id"]   = sensor_id
    if room_id:     tf["room_id"]     = room_id
    if building_id: tf["building_id"] = building_id
    if metric_type: tf["metric_type"] = metric_type
    return query_latest_readings(tf or None)


@router.get("/range")
def range_readings(start: str = "-24h",
                   stop: Optional[str] = None,
                   metric_type: Optional[str] = None,
                   building_id: Optional[str] = None,
                   floor_id:    Optional[str] = None,
                   room_id:     Optional[str] = None,
                   win:         str = "1h",
                   _=Depends(get_current_user)):
    return query_readings_range(start, stop, metric_type, building_id, floor_id, room_id, win)


@router.get("/dashboard")
def dashboard(_=Depends(get_current_user)):
    return query_dashboard_stats()