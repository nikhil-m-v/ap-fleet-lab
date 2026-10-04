import asyncio
from contextlib import asynccontextmanager
import multiprocessing as mp
from pathlib import Path
import queue
import time
import uuid
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .models import RunConfig, Scenario
from .geometry import validate_geometry
from .scenarios import make_scenario
from .storage import Store, read_replay
from .worker import run_worker


class Control(BaseModel):
    type: str
    robot: str | None = None
    seconds: float = Field(default=3, gt=0, le=60)


class Manager:
    def __init__(self):
        self.store = Store()
        self.jobs = {}
        self.last_save = {}

    def poll(self):
        for identifier, job in self.jobs.items():
            while True:
                try:
                    update = job["updates"].get_nowait()
                except queue.Empty:
                    break
                recent = (job["snapshot"].get("events", []) + update.get("events", []))[
                    -1000:
                ]
                job["snapshot"] = {**job["snapshot"], **update, "events": recent}
                terminal = update["status"] != "running"
                if terminal or time.monotonic() - self.last_save.get(identifier, 0) > 1:
                    self.store.save(identifier, job["snapshot"])
                    self.last_save[identifier] = time.monotonic()
            if not job["process"].is_alive() and job["snapshot"]["status"] in (
                "starting",
                "running",
            ):
                # Queue feeder may still be flushing; wait one poll before marking failure.
                if job.get("exited_at") is None:
                    job["exited_at"] = time.monotonic()
                elif time.monotonic() - job["exited_at"] > 1:
                    job["snapshot"].update(
                        status="failed", error="Worker exited without a terminal result"
                    )
                    self.store.save(identifier, job["snapshot"])

    def create(self, config):
        self.poll()
        if sum(j["process"].is_alive() for j in self.jobs.values()) >= 2:
            raise HTTPException(429, "At most two simulations can run concurrently")
        scenario = config.custom_scenario or make_scenario(
            config.scenario, config.fleet_size
        )
        try:
            validate_geometry(scenario)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        identifier = uuid.uuid4().hex
        context = mp.get_context("spawn")
        commands, updates = context.Queue(), context.Queue()
        snapshot = {
            "id": identifier,
            "status": "starting",
            "config": config.model_dump(),
            "scenario": scenario.model_dump(),
            "time": 0,
            "metrics": {},
            "robots": [],
            "created_at": time.time(),
        }
        process = context.Process(
            target=run_worker,
            args=(
                identifier,
                config.model_dump(),
                commands,
                updates,
                str(self.store.artifact(identifier)),
            ),
            daemon=True,
        )
        self.jobs[identifier] = {
            "process": process,
            "commands": commands,
            "updates": updates,
            "snapshot": snapshot,
        }
        self.store.save(identifier, snapshot)
        process.start()
        return snapshot

    def get(self, identifier):
        self.poll()
        snapshot = self.jobs.get(identifier, {}).get("snapshot") or self.store.get(
            identifier
        )
        if not snapshot:
            raise HTTPException(404, "Run not found")
        return snapshot

    def close(self):
        for identifier, job in self.jobs.items():
            if job["process"].is_alive():
                job["commands"].put({"type": "stop"})
                job["process"].join(timeout=2)
                if job["process"].is_alive():
                    job["process"].terminate()
                    job["process"].join()
        self.poll()


manager = None


@asynccontextmanager
async def lifespan(app):
    global manager
    manager = Manager()
    for old in manager.store.list():
        if old["status"] in ("starting", "running"):
            old.update(status="interrupted", error="Server restarted")
            manager.store.save(old["id"], old)

    async def collect():
        while True:
            manager.poll()
            await asyncio.sleep(0.1)

    collector = asyncio.create_task(collect())
    yield
    collector.cancel()
    manager.close()


app = FastAPI(title="AP Fleet Lab", lifespan=lifespan)


@app.get("/api/scenarios")
async def scenarios(fleet_size: int = 4):
    if not 2 <= fleet_size <= 32:
        raise HTTPException(422, "Fleet size must be 2–32")
    return [
        make_scenario(kind, fleet_size).model_dump()
        for kind in ("intersection", "corridor", "warehouse")
    ]


@app.post("/api/scenarios/validate")
async def validate(scenario: Scenario):
    try:
        validate_geometry(scenario)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"valid": True, "scenario": scenario.model_dump()}


@app.post("/api/runs", status_code=201)
async def create(config: RunConfig):
    return manager.create(config)


@app.get("/api/runs")
async def runs():
    manager.poll()
    return manager.store.list()


@app.get("/api/runs/{identifier}")
async def get_run(identifier: str):
    return manager.get(identifier)


@app.get("/api/runs/{identifier}/metrics")
async def metrics(identifier: str):
    return manager.get(identifier).get("metrics", {})


@app.post("/api/runs/{identifier}/control")
async def control(identifier: str, command: Control):
    snapshot = manager.get(identifier)
    if (
        snapshot["status"] not in ("running", "starting")
        or identifier not in manager.jobs
    ):
        raise HTTPException(409, "Run is not active")
    if command.type not in ("pause", "resume", "stop", "disrupt"):
        raise HTTPException(422, "Unknown command")
    if command.type == "disrupt" and command.robot not in {
        r["id"] for r in snapshot["scenario"]["robots"]
    }:
        raise HTTPException(422, "Unknown robot")
    manager.jobs[identifier]["commands"].put(command.model_dump())
    return {"queued": True}


@app.get("/api/runs/{identifier}/replay")
async def replay(identifier: str):
    snapshot = manager.get(identifier)
    if snapshot["status"] in ("running", "starting"):
        raise HTTPException(409, "Replay becomes available when the run finishes")
    file = manager.store.artifact(identifier)
    if not file.exists():
        raise HTTPException(404, "No replay artifact")
    return read_replay(file)


@app.get("/api/runs/{identifier}/export")
async def export(identifier: str):
    snapshot = manager.get(identifier)
    if snapshot["status"] in ("running", "starting"):
        raise HTTPException(409, "Finish the run before export")
    file = manager.store.artifact(identifier)
    if not file.exists():
        raise HTTPException(404, "No artifact")
    return FileResponse(
        file, filename=f"{identifier}.jsonl.gz", media_type="application/gzip"
    )


@app.websocket("/api/runs/{identifier}/stream")
async def stream(websocket: WebSocket, identifier: str):
    await websocket.accept()
    previous = None
    try:
        while True:
            try:
                snapshot = manager.get(identifier)
            except HTTPException:
                await websocket.send_json({"error": "Run not found"})
                break
            marker = (
                snapshot.get("time"),
                snapshot["status"],
                snapshot.get("paused"),
                snapshot.get("schedule_version"),
                len(snapshot.get("events", [])),
            )
            if marker != previous:
                await websocket.send_json(snapshot)
                previous = marker
            if snapshot["status"] not in ("starting", "running"):
                break
            await asyncio.sleep(0.1)
    except (WebSocketDisconnect, RuntimeError):
        pass


dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
