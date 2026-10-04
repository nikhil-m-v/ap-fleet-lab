# Design and mathematical formulation

## System

React/TypeScript renders a Canvas view and requests run controls. FastAPI manages REST and WebSocket access. Each run executes in a separate spawned process. The worker owns time, motion, admission, metrics, and compressed event recording. SQLite stores run metadata and final results. A restarted server marks unfinished runs as interrupted; artifacts remain available when readable.

At most two workers run concurrently. Simulation increments are at most 100 ms and stop exactly at movement completion and warm-up boundaries. Playback speed changes how many increments execute per wall-clock batch, not the simulation integrator. Pause freezes simulation time. The UI never modifies simulated positions.

## Motion and geometry

For each straight segment of length L, peak speed is min(v_max, sqrt(L a)). Acceleration/deceleration take v_peak/a; any remaining length is traveled at constant peak speed. Each phase is quadratic in time. Polyline corners require zero speed.

Random stops split the first segment at its midpoint, brake to zero, dwell, and accelerate again. This changes travel duration as well as adding dwell, and is not an instantaneous velocity discontinuity. Manual stops insert dwell at the next zero-speed corner/end of the active movement; waiting robots apply queued stops to the next traversal. Slowdowns lower maximum speed while retaining the acceleration limit.

Path incompatibility uses exact line-segment distances. A waiting bay must be at least r_i+r_j+clearance away from all other swept paths. Thus a waiting robot cannot block a moving robot, and an admitted movement does not acquire another permission before releasing its current permissions. A permanent externally imposed stop can cause indefinite blocking, but not a circular resource wait under this model.

## Periodic optimization

Use a scheduling tick of 0.1 seconds. For each traversal, d_ij = ceil(nominal_duration/0.1) + ceil(timing_margin/0.1). These are scheduling durations; actual physics is not rounded.

Choose integer period T and lifted starts s_ij. First starts obey 0 <= s_i0 < T. Route order obeys s_i,j+1 >= s_ij + d_ij. Every traversal must finish by s_i0 + T. Thus s_ij lies within two periods. The AP is s_ij+nT; φ_i=s_i0 and δ_ij=s_ij−s_i0.

For each incompatible pair A,B and k in {-2,-1,0,1,2}, enforce either:

```
s_A + d_A <= s_B + kT
or
s_B + kT + d_B <= s_A
```

More distant copies cannot intersect because all starts are in [0,2T) and each mission finishes within one period of its first start. Robot precedence also prevents self-overlap across repetitions. Reified Boolean constraints express the disjunction. Minimize T. A fully serial schedule provides a feasible upper bound and hint. Robot mission durations and greedy weighted cliques of incompatible traversals provide valid lower bounds.

Solver budgets constrain solver search, not preprocessing/model construction. Only OPTIMAL means optimal within this model. FEASIBLE includes the best bound and relative gap. UNKNOWN, INFEASIBLE, and MODEL_INVALID admit no periodic movements. There is no automatic algorithm fallback.

## Execution strategies

FCFS orders current requests by ready time then robot ID. Periodic admission orders eligible current traversal requests by scheduled entry then robot ID, while retaining delayed active permissions; no fixed global action-dependency graph is imposed. Thus this is an AP-guided, occupancy-gated execution policy, not a proof of preservation of all planned cross-robot orders after arbitrary delays.

A robot never starts a second mission while its current mission is incomplete. A unavailable first-leg slot advances to the next applicable cycle. Overdue later legs wait at their private bays. This first version does not lend empty slots or repair phases.

Rolling optimization uses one currently pending traversal per ready robot. Active movements and cooldowns impose fixed earliest starts on conflicting requests. Minimize makespan, then sum of start times using an integer objective multiplier. Replan when pending identities or active motions change. Active reservations remain immutable. This limited horizon is explicit so it cannot be confused with the established full rolling-horizon MAPF method.

All strategies enforce actual occupancy and the same cooldown margin. Safety does not rely on meeting planned timestamps.

## Independent verification

For each interval, a speed-bound broad phase excludes pairs that cannot approach within the required clearance. Remaining pairs split time at both robots' phase boundaries. Relative position is quadratic; squared separation is quartic, and its stationary points are roots of a cubic derivative. Evaluate endpoints and real roots within the interval. No reservation-graph information enters this checker. Floating-point tolerances are 1e-7 meters for violations; this is a numeric check, not formal verification.

## Public interfaces

- `Scenario`: name, clearance in meters, robots with IDs/radii/motion limits/closed traversal paths.
- `RunConfig`: scenario/template, fleet, algorithm, demand, seed, measurement/warm-up windows, disruption parameters, timing margin, solver budget, playback speed.
- `Scheduler.plan(scenario, state) -> PlanResult`: solver status, starts, optional period/bound/gap, elapsed planning time, diagnostics. Rolling state includes pending traversals and active remaining occupancy.
- `GET /api/scenarios?fleet_size=4`; `POST /api/scenarios/validate`.
- `POST /api/runs`; `GET /api/runs`; `GET /api/runs/{id}` and `/metrics`.
- `POST /api/runs/{id}/control`: pause/resume/stop/disrupt; disruption adds robot ID and seconds.
- `WS /api/runs/{id}/stream`: latest snapshots with recent events. Full event history lives in export artifacts.
- `GET /api/runs/{id}/replay` and `/export`: available after a terminal result.

Metrics exclude warm-up completions and traversal starts. Wait is request-to-admission time, including AP gating. Jain fairness is null with no completions. Queue growth is final minus warm-up queue size; saturated demand maintains one ready mission per idle robot rather than an infinite backlog. Mission recovery is time from the most recent injected stop's end to the affected mission's completion, not network-wide recovery. `minimum_checked_clearance` describes narrow-phase checks only, not a global separation minimum. Temporary blocking and >60s starvation observations are diagnostic, not proof of deadlock; deadlock count is zero by the private-bay admission model.
