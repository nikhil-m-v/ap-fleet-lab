import time
from fastapi.testclient import TestClient
from ap_fleet.api import app


def test_validation_run_controls_websocket_and_replay(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/scenarios?fleet_size=40").status_code == 422
        scenario = client.get("/api/scenarios?fleet_size=2").json()[0]
        assert client.post("/api/scenarios/validate", json=scenario).status_code == 200
        created = client.post(
            "/api/runs",
            json={
                "algorithm": "fcfs",
                "fleet_size": 2,
                "duration": 2,
                "playback_speed": 10,
            },
        )
        assert created.status_code == 201
        identifier = created.json()["id"]
        assert (
            client.post(
                f"/api/runs/{identifier}/control",
                json={"type": "disrupt", "robot": "unknown"},
            ).status_code
            == 422
        )
        assert client.get(f"/api/runs/{identifier}/replay").status_code == 409
        with client.websocket_connect(f"/api/runs/{identifier}/stream") as ws:
            snapshot = ws.receive_json()
            assert snapshot["id"] == identifier
        for _ in range(100):
            snapshot = client.get(f"/api/runs/{identifier}").json()
            if snapshot["status"] not in ("starting", "running"):
                break
            time.sleep(0.05)
        assert snapshot["status"] == "completed", snapshot
        replay = client.get(f"/api/runs/{identifier}/replay").json()
        assert replay["frames"][-1]["metrics"] == snapshot["metrics"]
        assert client.get(f"/api/runs/{identifier}/export").status_code == 200
        assert client.get("/api/runs/not-found").status_code == 404
