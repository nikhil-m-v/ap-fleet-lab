import argparse
import csv
import gzip
import itertools
import json
from pathlib import Path
import statistics
import sys
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from .models import RunConfig
from .scenarios import make_scenario
from .simulation import Simulation
from .storage import provenance


def execute(config, artifact=None):
    simulation = Simulation(config)
    stream = gzip.open(artifact, "wt", encoding="utf-8") if artifact else None
    cursor, last_frame = 0, -1.0

    def record(kind, data):
        if stream:
            stream.write(
                json.dumps({"kind": kind, "data": data}, allow_nan=False) + "\n"
            )

    metadata = provenance()
    record(
        "header",
        {
            "config": config.model_dump(),
            "scenario": simulation.scenario.model_dump(),
            "provenance": metadata,
        },
    )
    try:
        while True:
            if stream:
                for event in simulation.events[cursor:]:
                    record("event", event)
                cursor = len(simulation.events)
                if (
                    simulation.time - last_frame >= 0.2 - 1e-8
                    or simulation.status != "running"
                ):
                    record("frame", simulation.snapshot())
                    last_frame = simulation.time
            if simulation.status != "running":
                break
            simulation.step()
    finally:
        if stream:
            stream.close()
    return {
        "config": config.model_dump(),
        "status": simulation.status,
        "metrics": simulation.metrics(),
        "plan": simulation.plan.model_dump(),
        "provenance": metadata,
    }


def summarize(results, output):
    groups = {}
    for result in results:
        c = result["config"]
        key = (
            c["scenario"],
            c["fleet_size"],
            c["demand"],
            c["delay_probability"],
            c["slowdown_probability"],
            c["algorithm"],
        )
        groups.setdefault(key, []).append(result)
    rows = []
    for key, items in sorted(groups.items()):
        good = [r for r in items if r["status"] == "completed"]
        throughputs = [r["metrics"]["missions_per_minute"] for r in good]
        sem = (
            statistics.stdev(throughputs) / len(throughputs) ** 0.5
            if len(throughputs) > 1
            else None
        )
        rows.append(
            {
                "scenario": key[0],
                "fleet": key[1],
                "demand": key[2],
                "stop_probability": key[3],
                "slowdown_probability": key[4],
                "algorithm": key[5],
                "runs": len(items),
                "completed_runs": len(good),
                "throughput_mean": (
                    statistics.mean(throughputs) if throughputs else None
                ),
                "throughput_sd": (
                    statistics.stdev(throughputs) if len(throughputs) > 1 else None
                ),
                "throughput_approx_95ci_halfwidth": (
                    1.96 * sem if sem is not None else None
                ),
                "p95_wait_mean": (
                    statistics.mean(r["metrics"]["p95_wait_seconds"] for r in good)
                    if good
                    else None
                ),
                "planning_seconds_mean": (
                    statistics.mean(r["metrics"]["planning_seconds"] for r in good)
                    if good
                    else None
                ),
                "clearance_violations": sum(
                    r["metrics"]["clearance_violations"] for r in items
                ),
            }
        )
    if rows:
        with (output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    paired = {}
    for result in results:
        c = result["config"]
        key = (
            c["scenario"],
            c["fleet_size"],
            c["demand"],
            c["delay_probability"],
            c["slowdown_probability"],
            c["seed"],
        )
        if result["status"] == "completed":
            paired.setdefault(key, {})[c["algorithm"]] = result["metrics"][
                "missions_per_minute"
            ]
    comparisons = []
    for baseline in ("fcfs", "rolling"):
        for condition in sorted({key[:-1] for key in paired}):
            deltas = [
                values["periodic"] - values[baseline]
                for key, values in paired.items()
                if key[:-1] == condition and "periodic" in values and baseline in values
            ]
            if deltas:
                comparisons.append(
                    {
                        "condition": condition,
                        "baseline": baseline,
                        "paired_seeds": len(deltas),
                        "mean_throughput_delta": statistics.mean(deltas),
                        "wins": sum(d > 1e-9 for d in deltas),
                        "ties": sum(abs(d) <= 1e-9 for d in deltas),
                        "losses": sum(d < -1e-9 for d in deltas),
                    }
                )
    (output / "paired-comparisons.json").write_text(
        json.dumps(comparisons, indent=2), encoding="utf-8"
    )
    lines = [
        "# Benchmark report",
        "",
        "Generated from seeded experiments; no claim of general superiority.",
        "",
        "| Environment | Fleet | Demand | Stops / slowdown | Strategy | Finished | Missions/min ± SD | Mean p95 wait |",
        "|---|---:|---|---|---|---:|---:|---:|",
    ]
    for row in rows:
        mean = row["throughput_mean"]
        sd = row["throughput_sd"]
        tp = (
            f"{mean:.3f} ± {sd:.3f}"
            if sd is not None
            else f"{mean:.3f}" if mean is not None else "unavailable"
        )
        wait = (
            f"{row['p95_wait_mean']:.2f}s"
            if row["p95_wait_mean"] is not None
            else "unavailable"
        )
        lines.append(
            f"| {row['scenario']} | {row['fleet']} | {row['demand']} | {row['stop_probability']} / {row['slowdown_probability']} | {row['algorithm']} | {row['completed_runs']}/{row['runs']} | {tp} | {wait} |"
        )
    lines.extend(
        [
            "",
            "## Paired AP comparisons",
            "",
            "Positive deltas favor periodic scheduling. Failed runs are excluded from paired comparisons and retained in the summary.",
            "",
        ]
    )
    for c in comparisons:
        lines.append(
            f"- {c['condition']}: AP − {c['baseline']} = {c['mean_throughput_delta']:.3f} missions/min; {c['wins']} wins, {c['ties']} ties, {c['losses']} losses ({c['paired_seeds']} seeds)."
        )
    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "Whole-traversal exclusion is conservative. Rolling optimization covers one pending traversal per ready robot, not full multi-agent pathfinding. Common-period AP gives every robot one mission per cycle. Stop randomness is keyed by robot, mission and leg; mission start times differ between schedulers. Sampled completion counts depend on measurement boundaries. Zero observed collisions is a simulation result, not hardware certification.",
            "",
            "See results.jsonl for measurement windows, solver status/gaps, dependency versions and commit state. Approximate confidence intervals in summary.csv assume independent seeds; they are not corrected for multiple comparisons.",
        ]
    )
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="AP Fleet Lab reproducible experiment runner"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    run = sub.add_parser("run")
    run.add_argument(
        "--algorithm", choices=["fcfs", "periodic", "rolling"], default="periodic"
    )
    run.add_argument("--scenario", default="intersection")
    run.add_argument("--fleet", type=int, default=4)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--duration", type=float, default=120)
    run.add_argument("--warmup", type=float, default=0)
    run.add_argument("--artifact", type=Path)
    bench = sub.add_parser("benchmark")
    bench.add_argument(
        "--scenarios", nargs="+", default=["intersection", "corridor", "warehouse"]
    )
    bench.add_argument("--fleets", nargs="+", type=int, default=[4, 8, 16, 32])
    bench.add_argument(
        "--demands", nargs="+", default=["saturated", "intermittent", "bursts"]
    )
    bench.add_argument(
        "--profiles", nargs="+", choices=["none", "mixed"], default=["none", "mixed"]
    )
    bench.add_argument("--seeds", type=int, default=20)
    bench.add_argument("--duration", type=float, default=600)
    bench.add_argument("--warmup", type=float, default=60)
    bench.add_argument("--solver-budget", type=float, default=2)
    bench.add_argument("--output", type=Path, default=Path("benchmark-output"))
    bench.add_argument("--resume", action="store_true")
    bench.add_argument("--workers", type=int, default=1)
    samples = sub.add_parser("scenarios")
    samples.add_argument("--output", type=Path, default=Path("src/ap_fleet/scenarios"))
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run("ap_fleet.api:app", host="127.0.0.1", port=args.port)
    elif args.command == "run":
        if args.artifact:
            args.artifact.parent.mkdir(parents=True, exist_ok=True)
        result = execute(
            RunConfig(
                algorithm=args.algorithm,
                scenario=args.scenario,
                fleet_size=args.fleet,
                seed=args.seed,
                duration=args.duration,
                warmup=args.warmup,
            ),
            args.artifact,
        )
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "completed" else 1)
    elif args.command == "scenarios":
        args.output.mkdir(parents=True, exist_ok=True)
        for kind in ("intersection", "corridor", "warehouse"):
            (args.output / f"{kind}.json").write_text(
                make_scenario(kind).model_dump_json(indent=2), encoding="utf-8"
            )
    else:
        if args.seeds < 1 or not 1 <= args.workers <= 8:
            parser.error("--seeds must be positive and --workers must be 1–8")
        args.output.mkdir(parents=True, exist_ok=True)
        file = args.output / "results.jsonl"
        if file.exists() and not args.resume:
            parser.error(
                "Output already exists; choose a new directory or use --resume"
            )
        results = (
            [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()]
            if file.exists()
            else []
        )
        completed = {json.dumps(r["config"], sort_keys=True) for r in results}
        cases = list(
            itertools.product(
                args.scenarios,
                args.fleets,
                args.demands,
                args.profiles,
                range(args.seeds),
                ("fcfs", "periodic", "rolling"),
            )
        )
        jobs = []
        for index, (scenario, fleet, demand, profile, seed, algorithm) in enumerate(
            cases
        ):
            config = RunConfig(
                scenario=scenario,
                fleet_size=fleet,
                demand=demand,
                seed=seed,
                algorithm=algorithm,
                duration=args.duration,
                warmup=args.warmup,
                solver_budget=args.solver_budget,
                delay_probability=0.15 if profile == "mixed" else 0,
                slowdown_probability=0.1 if profile == "mixed" else 0,
            )
            if json.dumps(config.model_dump(), sort_keys=True) not in completed:
                jobs.append((index, config))
        try:
            with file.open("a", encoding="utf-8") as stream:

                def accept(index, result):
                    results.append(result)
                    result["provenance"]["benchmark_workers"] = args.workers
                    stream.write(json.dumps(result, allow_nan=False) + "\n")
                    stream.flush()
                    c = result["config"]
                    print(
                        f"[{len(results)}/{len(cases)}] {c['scenario']}/{c['fleet_size']}/{c['demand']} seed={c['seed']} {c['algorithm']}: {result['status']} {result['metrics']['missions_per_minute']:.3f} missions/min",
                        flush=True,
                    )

                if args.workers == 1:
                    for index, config in jobs:
                        accept(index, execute(config))
                else:
                    iterator = iter(jobs)
                    with ProcessPoolExecutor(
                        max_workers=args.workers, mp_context=mp.get_context("spawn")
                    ) as pool:
                        futures = {}

                        def submit_next():
                            item = next(iterator, None)
                            if item is not None:
                                index, config = item
                                futures[pool.submit(execute, config)] = index

                        for _ in range(args.workers * 2):
                            submit_next()
                        while futures:
                            done, _ = wait(futures, return_when=FIRST_COMPLETED)
                            for future in done:
                                accept(futures.pop(future), future.result())
                                submit_next()
        finally:
            summarize(results, args.output)


if __name__ == "__main__":
    main()
