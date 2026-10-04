"""Generate scientific figures and an overview from completed raw experiments."""

import csv
import gzip
import json
from pathlib import Path
import sys
import platform
import os
import importlib.metadata
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/results/full")
environment = {
    "python": platform.python_version(),
    "os": platform.platform(),
    "machine": platform.machine(),
    "logical_cpus": os.cpu_count(),
    "benchmark_workers": 4,
    "solver_search_workers": 1,
    "packages": {
        distribution.metadata["Name"]: distribution.version
        for distribution in importlib.metadata.distributions()
    },
}
(root / "environment.json").write_text(
    json.dumps(environment, indent=2), encoding="utf-8"
)
rows = list(csv.DictReader((root / "summary.csv").open(encoding="utf-8")))
colors = {"fcfs": "#6590b0", "periodic": "#219879", "rolling": "#ca8d46"}
labels = {"fcfs": "FCFS", "periodic": "AP periodic", "rolling": "Rolling window"}
plt.rcParams.update(
    {
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.labelcolor": "#354b47",
        "text.color": "#354b47",
        "figure.facecolor": "white",
    }
)
for demand in ("saturated", "intermittent", "bursts"):
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), layout="constrained")
    for column, scenario in enumerate(("intersection", "corridor", "warehouse")):
        for index, profile in enumerate(("0.0", "0.15")):
            ax = axes[index, column]
            for algorithm in colors:
                subset = sorted(
                    [
                        r
                        for r in rows
                        if r["scenario"] == scenario
                        and r["demand"] == demand
                        and r["stop_probability"] == profile
                        and r["algorithm"] == algorithm
                        and r["throughput_mean"]
                    ],
                    key=lambda r: int(r["fleet"]),
                )
                xs = [int(r["fleet"]) for r in subset]
                means = [float(r["throughput_mean"]) for r in subset]
                errors = [float(r["throughput_sd"] or 0) for r in subset]
                ax.errorbar(
                    xs,
                    means,
                    yerr=errors,
                    label=labels[algorithm],
                    color=colors[algorithm],
                    marker="o",
                    capsize=3,
                    linewidth=1.6,
                )
            ax.set_title(
                scenario.capitalize()
                + (" · no disruption" if index == 0 else " · stops + slowdowns")
            )
            ax.set_xticks([4, 8, 16, 32])
            ax.set_xlabel("Robots")
            ax.set_ylabel("Completed missions / minute")
            ax.grid(alpha=0.15)
    axes[0, 0].legend(frameon=False, fontsize=9)
    fig.suptitle(
        f"AP Fleet Lab · {demand} demand\nMean ± sample SD across 20 paired seeds; 60s warm-up + 600s measurement",
        fontsize=13,
    )
    fig.savefig(root / f"{demand}.png", dpi=180)
    fig.savefig(root / f"{demand}.svg")
    plt.close(fig)
raw = root / "results.jsonl"
with gzip.open(root / "results.jsonl.gz", "wt", encoding="utf-8") as stream:
    stream.write(raw.read_text(encoding="utf-8"))
results = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
violations = sum(r["metrics"]["clearance_violations"] for r in results)
failures = sum(r["status"] != "completed" for r in results)
comparisons = json.loads((root / "paired-comparisons.json").read_text(encoding="utf-8"))
lines = [
    "# Experiment overview",
    "",
    f"Executed **{len(results):,} runs**: 20 paired seeds for all 72 environment/fleet/demand/disruption conditions, using three strategies. {failures} runs did not complete; {violations} continuous clearance violations were observed.",
    "",
    "The experiment uses four worker processes and a two-second budget for each solver call. Planning latency includes model construction. Raw records preserve source revision, dirty state, dependency versions, configuration and solver status. Earlier solver cases and intermittent-demand cases were regenerated after exact clique reductions and fleet-normalized arrivals; the benchmark is not a single-revision historical dataset.",
    "",
    "## AP comparisons",
    "",
    "Counts below compare the AP throughput to each baseline for individual paired seeds, using a 1e-9 missions/min tie tolerance. They do not establish general superiority.",
    "",
    "| Baseline | AP wins | Ties | AP losses |",
    "|---|---:|---:|---:|",
]
for baseline in ("fcfs", "rolling"):
    selected = [c for c in comparisons if c["baseline"] == baseline]
    lines.append(
        f"| {baseline} | {sum(c['wins'] for c in selected)} | {sum(c['ties'] for c in selected)} | {sum(c['losses'] for c in selected)} |"
    )
lines.extend(
    [
        "",
        "## Finite-window caveat",
        "",
        "At larger fleets, the shared period can exceed the complete 660-second run. FCFS may perform first traversals for many robots before any complete mission, while AP's initial hint groups a robot's traversals. Mission-completion throughput and fairness can therefore reflect initialization and measurement boundaries. Do not interpret those cases as steady-state capacity. Future experiments should warm up for several computed cycles, then measure many more cycles.",
        "",
        "## Figures",
        "",
        "![Saturated demand](saturated.png)",
        "",
        "![Intermittent demand](intermittent.png)",
        "",
        "![Bursty demand](bursts.png)",
        "",
        "See [full tables](report.md), [CSV summary](summary.csv), [paired comparisons](paired-comparisons.json), and [compressed raw records](results.jsonl.gz). Whole-traversal serialization and private bays limit applicability; no physical controller was tested.",
    ]
)
(root / "overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("Generated plots, overview, and compressed raw results")
