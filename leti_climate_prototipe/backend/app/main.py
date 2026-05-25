import asyncio
import logging
import math
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import auth, buildings, floors, rooms, sensors, readings, io
from app.auth import get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

READING_INTERVAL_SECONDS = 30 * 60  # генерировать новую синтетическую точку каждые 30 минут


def _rand_value(metric: str, hour: int) -> float:
    """Synthetic realistic value with daily cycle — mirrors seed.py."""
    if metric == "temperature":
        return round(22.0 + 2 * math.sin(math.pi * hour / 12) + random.uniform(-0.5, 0.5), 1)
    if metric == "humidity":
        return round(50.0 + 5 * math.sin(math.pi * hour / 12) + random.uniform(-2, 2), 1)
    if metric == "co2":
        occupied = 1 if 8 <= hour <= 18 else 0
        return round(400 + 300 * occupied + random.uniform(-20, 20), 1)
    return 0.0


async def _synthetic_readings_loop():
    """Background task: write one synthetic reading per active sensor every 30 min."""
    from app.influx import query_entities, write_entities_batch, write_reading

    await asyncio.sleep(60)

    while True:
        try:
            all_sensors = query_entities("sensors", "sensor_id")
            now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            points = []

            for s in all_sensors:
                val = _rand_value(s["metric_type"], now.hour)
                pt  = write_reading(
                    s["id"], s["room_id"], s["floor_id"], s["building_id"],
                    s["metric_type"], val, s["status"], now,
                )
                points.append(pt)

            if points:
                write_entities_batch(points)
                logger.info(
                    "Synthetic readings written: %d points at %s",
                    len(points), now.isoformat(),
                )
        except Exception as exc:
            logger.error("Synthetic readings loop error: %s", exc)

        await asyncio.sleep(READING_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Waiting for InfluxDB to be ready …")
    await asyncio.sleep(3)

    try:
        from app.seed import seed_if_empty
        seed_if_empty()
    except Exception as exc:
        logger.error("Seed error: %s", exc)

    task = asyncio.create_task(_synthetic_readings_loop())
    logger.info("Synthetic readings background task started.")

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="ЛЭТИ — Микроклимат", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,      prefix="/api/auth",      tags=["auth"])
app.include_router(buildings.router, prefix="/api/buildings", tags=["buildings"])
app.include_router(floors.router,    prefix="/api/floors",    tags=["floors"])
app.include_router(rooms.router,     prefix="/api/rooms",     tags=["rooms"])
app.include_router(sensors.router,   prefix="/api/sensors",   tags=["sensors"])
app.include_router(readings.router,  prefix="/api/readings",  tags=["readings"])
app.include_router(io.router,        prefix="/api",           tags=["io"])


@app.get("/api/seed/status", tags=["system"])
async def seed_status(_=Depends(get_current_user)):
    try:
        from app.influx import query_entities
        buildings = query_entities("buildings", "building_id")
        return {"ready": len(buildings) > 0, "count": len(buildings)}
    except Exception:
        return {"ready": False, "count": 0}


app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")