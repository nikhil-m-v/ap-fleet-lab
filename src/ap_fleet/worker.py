import gzip
import json
import queue
import time
from .models import RunConfig
from .simulation import Simulation
from .storage import provenance


def run_worker(identifier, config, commands, updates, artifact):
    try:
        simulation = Simulation(RunConfig.model_validate(config))
        paused = False
        last_frame = -1.0
        cursor = 0
        with gzip.open(artifact, "wt", encoding="utf-8") as stream:

            def record(kind, data):
                stream.write(
                    json.dumps({"kind": kind, "data": data}, allow_nan=False) + "\n"
                )

            record(
                "header",
                {
                    "config": config,
                    "scenario": simulation.scenario.model_dump(),
                    "provenance": provenance(),
                },
            )
            while True:
                tick_start = time.monotonic()
                while True:
                    try:
                        command = commands.get_nowait()
                    except queue.Empty:
                        break
                    kind = command["type"]
                    if kind == "pause":
                        paused = True
                    elif kind == "resume":
                        paused = False
                    elif kind == "stop":
                        simulation.status = "cancelled"
                    elif kind == "disrupt":
                        simulation.inject(command["robot"], command["seconds"])
                if not paused and simulation.status == "running":
                    # Every speed uses the same deterministic 100 ms integrator.
                    steps = max(1, round(simulation.config.playback_speed * 0.05 / 0.1))
                    for _ in range(steps):
                        if not simulation.step():
                            break
                snapshot = simulation.snapshot()
                snapshot["paused"] = paused
                snapshot["id"] = identifier
                snapshot["events"] = simulation.events[cursor:]
                for event in simulation.events[cursor:]:
                    record("event", event)
                cursor = len(simulation.events)
                if (
                    simulation.time - last_frame >= 0.2 - 1e-8
                    or last_frame < 0
                    or simulation.status != "running"
                ):
                    record("frame", snapshot)
                    last_frame = simulation.time
                updates.put(snapshot)
                if simulation.status != "running":
                    break
                time.sleep(max(0.0, 0.05 - (time.monotonic() - tick_start)))
    except Exception as exc:
        updates.put({"id": identifier, "status": "failed", "error": str(exc)})
