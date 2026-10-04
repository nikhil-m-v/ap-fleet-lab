"""Refresh pre-reduction solvers and pre-normalization intermittent demand."""

from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing as mp
from pathlib import Path
from ap_fleet.cli import execute, summarize
from ap_fleet.models import RunConfig


def main():
    root = Path("docs/results/full")
    file = root / "results.jsonl"
    results = [
        json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()
    ]
    indices = [
        i
        for i, result in enumerate(results)
        if (
            result["config"]["algorithm"] == "rolling"
            and result["provenance"]["commit"].startswith("4a75ab7")
        )
        or (
            result["config"]["algorithm"] == "periodic"
            and not any(
                "Exact independent clique certificate" in message
                for message in result["plan"]["diagnostics"]
            )
        )
        or (
            result["config"]["demand"] == "intermittent"
            and result.get("demand_model") != "fleet-normalized-v1"
        )
    ]
    configs = [RunConfig.model_validate(results[i]["config"]) for i in indices]
    with ProcessPoolExecutor(max_workers=4, mp_context=mp.get_context("spawn")) as pool:
        for n, (index, result) in enumerate(zip(indices, pool.map(execute, configs))):
            result["provenance"]["benchmark_workers"] = 4
            results[index] = result
            print(f"Refreshed experiment {n+1}/{len(indices)}", flush=True)
    temp = root / "refreshed.jsonl"
    temp.write_text(
        "".join(json.dumps(result, allow_nan=False) + "\n" for result in results),
        encoding="utf-8",
    )
    temp.replace(file)
    summarize(results, root)


if __name__ == "__main__":
    main()
