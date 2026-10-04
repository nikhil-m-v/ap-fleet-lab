# Research extensions

These experiments are intentionally not implemented in v0.1. The baseline must first establish where AP helps or hurts. None is claimed to be unexplored.

## 1. Safe reuse of empty slots

When a scheduled robot lacks a mission, test whether another ready robot can complete an entire traversal before the next protected incompatible reservation. Preserve active permissions, future committed entries, and the borrower's return-to-private-bay condition. Compare with an identical borrowing policy on a nonperiodic schedule; otherwise the benefit may come from borrowing rather than AP.

Measure throughput gain, missed protected slots, per-robot wait, and admission-check cost. Reject a borrowing request when uncertainty exceeds the available window.

## 2. Local phase repair after disruption

Use the movement conflict graph to select a repair neighborhood, then shift starts for unstarted traversals while active movements and boundary reservations stay fixed. Expand the neighborhood if infeasible. Compare with full reoptimization under the same solver budget. Dependency consistency is essential: a local change must not invalidate a neighboring cycle.

Measure repair latency, number of changed reservations, throughput, and fairness. Compare periodic-only, periodic+local repair, and periodic+global repair.

## 3. Bottleneck-specific timing margins

Estimate traversal overrun distributions from training seeds and allocate buffers under a fixed total slack budget. Evaluate on held-out seeds. Compare uniform, bottleneck-weighted, and empirical-quantile margins. Margins influence efficiency; actual occupancy gates remain responsible for safety outside the estimated delay bound.

## 4. Compact modular reservation representation

Store (offset, period, occupancy duration) plus exceptions instead of expanding every cycle. Measure memory and query cost against explicit interval lists as simulated duration grows. Include exceptions, cycle-boundary intervals, and unequal-period cases. Do not use coprime periods as a collision-prevention shortcut: their integer entry-time progressions eventually intersect.

## 5. Heterogeneous mission frequencies

A single shared period assigns equal cycle frequency. Explore harmonic subperiods or multiple missions per supercycle, with an explicit minimum-service constraint for every robot. Check fairness and hyperperiod growth. Benchmarks should separate saturated demand, uneven demand, and different route lengths.

Before making a novelty claim, compare against periodic MAPP, cyclic robot coordination, robust continuous-time MAPF, action/temporal dependency graphs, cyclic job-shop scheduling, and periodic railway timetabling. A reproducible negative result is preferable to an unsupported novelty claim.
