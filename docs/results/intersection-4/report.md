# Benchmark report

Generated from seeded experiments; no claim of general superiority.

| Environment | Fleet | Demand | Stops / slowdown | Strategy | Finished | Missions/min ± SD | Mean p95 wait |
|---|---:|---|---|---|---:|---:|---:|
| intersection | 4 | bursts | 0.0 / 0.0 | fcfs | 20/20 | 3.100 ± 0.000 | 0.00s |
| intersection | 4 | bursts | 0.0 / 0.0 | periodic | 20/20 | 3.100 ± 0.000 | 58.40s |
| intersection | 4 | bursts | 0.0 / 0.0 | rolling | 20/20 | 3.100 ± 0.000 | 0.00s |
| intersection | 4 | bursts | 0.15 / 0.1 | fcfs | 20/20 | 2.870 ± 0.080 | 0.00s |
| intersection | 4 | bursts | 0.15 / 0.1 | periodic | 20/20 | 2.835 ± 0.104 | 69.49s |
| intersection | 4 | bursts | 0.15 / 0.1 | rolling | 20/20 | 2.865 ± 0.088 | 0.00s |
| intersection | 4 | intermittent | 0.0 / 0.0 | fcfs | 20/20 | 3.100 ± 0.000 | 6.87s |
| intersection | 4 | intermittent | 0.0 / 0.0 | periodic | 20/20 | 3.085 ± 0.037 | 58.40s |
| intersection | 4 | intermittent | 0.0 / 0.0 | rolling | 20/20 | 3.100 ± 0.000 | 13.83s |
| intersection | 4 | intermittent | 0.15 / 0.1 | fcfs | 20/20 | 2.860 ± 0.082 | 9.53s |
| intersection | 4 | intermittent | 0.15 / 0.1 | periodic | 20/20 | 2.825 ± 0.102 | 69.44s |
| intersection | 4 | intermittent | 0.15 / 0.1 | rolling | 20/20 | 2.880 ± 0.089 | 12.26s |
| intersection | 4 | saturated | 0.0 / 0.0 | fcfs | 20/20 | 3.100 ± 0.000 | 0.00s |
| intersection | 4 | saturated | 0.0 / 0.0 | periodic | 20/20 | 3.100 ± 0.000 | 58.40s |
| intersection | 4 | saturated | 0.0 / 0.0 | rolling | 20/20 | 3.100 ± 0.000 | 0.00s |
| intersection | 4 | saturated | 0.15 / 0.1 | fcfs | 20/20 | 2.870 ± 0.073 | 0.00s |
| intersection | 4 | saturated | 0.15 / 0.1 | periodic | 20/20 | 2.835 ± 0.104 | 69.55s |
| intersection | 4 | saturated | 0.15 / 0.1 | rolling | 20/20 | 2.875 ± 0.079 | 0.00s |

## Paired AP comparisons

Positive deltas favor periodic scheduling. Failed runs are excluded from paired comparisons and retained in the summary.

- ('intersection', 4, 'bursts', 0.0, 0.0): AP − fcfs = -0.000 missions/min; 0 wins, 20 ties, 0 losses (20 seeds).
- ('intersection', 4, 'bursts', 0.15, 0.1): AP − fcfs = -0.035 missions/min; 5 wins, 6 ties, 9 losses (20 seeds).
- ('intersection', 4, 'intermittent', 0.0, 0.0): AP − fcfs = -0.015 missions/min; 0 wins, 17 ties, 3 losses (20 seeds).
- ('intersection', 4, 'intermittent', 0.15, 0.1): AP − fcfs = -0.035 missions/min; 5 wins, 6 ties, 9 losses (20 seeds).
- ('intersection', 4, 'saturated', 0.0, 0.0): AP − fcfs = -0.000 missions/min; 0 wins, 20 ties, 0 losses (20 seeds).
- ('intersection', 4, 'saturated', 0.15, 0.1): AP − fcfs = -0.035 missions/min; 5 wins, 6 ties, 9 losses (20 seeds).
- ('intersection', 4, 'bursts', 0.0, 0.0): AP − rolling = -0.000 missions/min; 0 wins, 20 ties, 0 losses (20 seeds).
- ('intersection', 4, 'bursts', 0.15, 0.1): AP − rolling = -0.030 missions/min; 5 wins, 6 ties, 9 losses (20 seeds).
- ('intersection', 4, 'intermittent', 0.0, 0.0): AP − rolling = -0.015 missions/min; 0 wins, 17 ties, 3 losses (20 seeds).
- ('intersection', 4, 'intermittent', 0.15, 0.1): AP − rolling = -0.055 missions/min; 2 wins, 10 ties, 8 losses (20 seeds).
- ('intersection', 4, 'saturated', 0.0, 0.0): AP − rolling = -0.000 missions/min; 0 wins, 20 ties, 0 losses (20 seeds).
- ('intersection', 4, 'saturated', 0.15, 0.1): AP − rolling = -0.040 missions/min; 4 wins, 7 ties, 9 losses (20 seeds).

## Interpretation limits

Whole-traversal exclusion is conservative. Rolling optimization covers one pending traversal per ready robot, not full multi-agent pathfinding. Common-period AP gives every robot one mission per cycle. Stop randomness is keyed by robot, mission and leg; mission start times differ between schedulers. Sampled completion counts depend on measurement boundaries. Zero observed collisions is a simulation result, not hardware certification.

See results.jsonl for measurement windows, solver status/gaps, dependency versions and commit state. Approximate confidence intervals in summary.csv assume independent seeds; they are not corrected for multiple comparisons.
