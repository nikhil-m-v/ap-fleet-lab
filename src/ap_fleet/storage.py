import gzip
import json
import sqlite3
from pathlib import Path
import importlib.metadata
import subprocess


def provenance():
    versions = {}
    for package in ("ap-fleet-lab", "numpy", "ortools", "fastapi", "uvicorn"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unavailable"
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        dirty = bool(
            subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {"versions": versions, "commit": commit, "dirty": dirty}


class Store:
    def __init__(self, directory="data"):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "runs.sqlite"
        with sqlite3.connect(self.database) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    def save(self, identifier, payload):
        with sqlite3.connect(self.database) as db:
            db.execute(
                "INSERT OR REPLACE INTO runs VALUES (?,?)",
                (identifier, json.dumps(payload, allow_nan=False)),
            )

    def get(self, identifier):
        with sqlite3.connect(self.database) as db:
            row = db.execute(
                "SELECT payload FROM runs WHERE id=?", (identifier,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self):
        with sqlite3.connect(self.database) as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM runs ORDER BY rowid DESC LIMIT 100"
                )
            ]

    def artifact(self, identifier):
        return self.root / f"{identifier}.jsonl.gz"


def read_replay(file):
    with gzip.open(file, "rt", encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream]
    return {
        "header": next((r for r in records if r["kind"] == "header"), None),
        "frames": [r["data"] for r in records if r["kind"] == "frame"],
        "events": [r["data"] for r in records if r["kind"] == "event"],
    }
