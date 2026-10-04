import math
import time
from fractions import Fraction
from ortools.sat.python import cp_model
from .models import PlanResult
from .motion import nominal_duration

TICK = 0.1


def ticks(seconds):
    return max(1, math.ceil(seconds / TICK - 1e-9))


def solver_for(budget):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = budget
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    return solver


def nonoverlap(model, a, da, b, db, label):
    before = model.new_bool_var(label)
    model.add(a + da <= b).only_enforce_if(before)
    model.add(b + db <= a).only_enforce_if(before.Not())


class FCFSScheduler:
    def plan(self, scenario, state=None):
        return PlanResult(
            status="REACTIVE",
            diagnostics=["FCFS admission, deterministic request-time / robot-ID order"],
        )


class PeriodicScheduler:
    def __init__(self, conflicts, margin=0.2, budget=2, max_period=None):
        self.conflicts, self.margin, self.budget = conflicts, margin, budget
        self.max_period = max_period

    def plan(self, scenario, state=None):
        began = time.perf_counter()
        guard = math.ceil(self.margin / TICK - 1e-9)
        durations = {
            (r.id, j): ticks(nominal_duration(r, j)) + guard
            for r in scenario.robots
            for j in range(len(r.legs))
        }
        upper = sum(durations.values())
        lower = max(
            sum(durations[r.id, j] for j in range(len(r.legs))) for r in scenario.robots
        )
        # Any clique of mutually exclusive traversals consumes that much of every
        # period. A greedy clique bound is valid even when it is not maximum.
        keys = sorted(durations, key=lambda key: (-durations[key], key))
        for seed in keys:
            clique = [seed]
            for key in keys:
                if key not in clique and all(
                    key[0] == other[0] or frozenset((key, other)) in self.conflicts
                    for other in clique
                ):
                    clique.append(key)
            lower = max(lower, sum(durations[key] for key in clique))
        model = cp_model.CpModel()
        period = model.new_int_var(lower, upper, "period")
        if self.max_period is not None:
            model.add(period <= math.floor(self.max_period / TICK))
        starts = {
            key: model.new_int_var(0, 2 * upper, "start_" + str(key))
            for key in durations
        }
        offset = 0
        model.add_hint(period, upper)
        for robot in scenario.robots:
            first = starts[robot.id, 0]
            model.add(first < period)
            for j in range(len(robot.legs)):
                key = robot.id, j
                if j:
                    model.add(
                        starts[key]
                        >= starts[robot.id, j - 1] + durations[robot.id, j - 1]
                    )
                model.add(starts[key] + durations[key] <= first + period)
                model.add_hint(starts[key], offset)
                offset += durations[key]
        for index, pair in enumerate(sorted(self.conflicts, key=lambda p: sorted(p))):
            a, b = sorted(pair)
            for shift in range(-2, 3):
                nonoverlap(
                    model,
                    starts[a],
                    durations[a],
                    starts[b] + shift * period,
                    durations[b],
                    f"order_{index}_{shift}",
                )
        model.minimize(period)
        solver = solver_for(self.budget)
        result = solver.solve(model)
        status = solver.status_name(result)
        elapsed = time.perf_counter() - began
        if result not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return PlanResult(
                status=status,
                planning_seconds=elapsed,
                diagnostics=["No feasible plan returned; admission disabled"],
            )
        objective = solver.value(period) * TICK
        bound = solver.best_objective_bound * TICK
        return PlanResult(
            status=status,
            starts={
                r.id: [solver.value(starts[r.id, j]) * TICK for j in range(len(r.legs))]
                for r in scenario.robots
            },
            period=objective,
            lower_bound=bound,
            optimality_gap=max(0.0, (objective - bound) / objective),
            planning_seconds=elapsed,
            diagnostics=[
                "Common period; exclusive complete traversals; ±2 cycle checks"
            ],
        )


class RollingScheduler:
    """Optimize the currently pending movements, with active movements frozen.

    Horizon ends after one pending traversal per ready robot. Replan on admissions,
    completions, demand changes, and disruptions; never alter an active movement.
    """

    def __init__(self, conflicts, margin=0.2, budget=2):
        self.conflicts, self.margin, self.budget = conflicts, margin, budget

    def plan(self, scenario, state=None):
        if state is None or not state["pending"]:
            return PlanResult(status="IDLE")
        began = time.perf_counter()
        pending = state["pending"]
        guard = math.ceil(self.margin / TICK - 1e-9)
        robots = {r.id: r for r in scenario.robots}
        durations = {
            key: ticks(nominal_duration(robots[key[0]], key[1])) + guard
            for key in pending
        }
        active = state["active"]
        frozen_end = max((ticks(remaining) for _, remaining in active), default=0)
        upper = sum(durations.values()) + frozen_end + guard + 1
        model = cp_model.CpModel()
        starts = {key: model.new_int_var(0, upper, "s_" + str(key)) for key in pending}
        releases = {key: 0 for key in pending}
        for key in pending:
            for frozen, remaining in active:
                if key[0] == frozen[0] or frozenset((key, frozen)) in self.conflicts:
                    model.add(starts[key] >= ticks(remaining))
                    releases[key] = max(releases[key], ticks(remaining))
        for index, a in enumerate(pending):
            for b in pending[index + 1 :]:
                if frozenset((a, b)) in self.conflicts:
                    nonoverlap(
                        model,
                        starts[a],
                        durations[a],
                        starts[b],
                        durations[b],
                        str((a, b)),
                    )
        finish = model.new_int_var(0, upper, "finish")
        for key in pending:
            model.add(finish >= starts[key] + durations[key])
        # Makespan first, then total completion time. Requests are sorted FCFS before
        # variable creation; this tie-break is deterministic, not a fairness proof.
        weights = {key: len(pending) - index for index, key in enumerate(pending)}
        # An isolated clique with equal releases is a single-machine problem.
        # Smith's duration/weight order minimizes weighted start/completion time,
        # and its non-idling schedule also minimizes makespan. Fixing that exact
        # optimum avoids factorial CP search; general components remain free.
        unseen = set(pending)
        reductions = 0
        while unseen:
            seed = min(unseen)
            component, frontier = {seed}, [seed]
            unseen.remove(seed)
            while frontier:
                node = frontier.pop()
                neighbors = {
                    key for key in unseen if frozenset((key, node)) in self.conflicts
                }
                component.update(neighbors)
                unseen.difference_update(neighbors)
                frontier.extend(neighbors)
            clique = all(
                frozenset((a, b)) in self.conflicts
                for a in component
                for b in component
                if a != b
            )
            if clique and len({releases[key] for key in component}) == 1:
                at = releases[seed]
                for key in sorted(
                    component,
                    key=lambda key: (Fraction(durations[key], weights[key]), key),
                ):
                    model.add(starts[key] == at)
                    at += durations[key]
                reductions += 1
        model.minimize(
            finish * (sum(weights.values()) * upper + 1)
            + sum(weights[key] * starts[key] for key in pending)
        )
        solver = solver_for(self.budget)
        result = solver.solve(model)
        if result not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return PlanResult(
                status=solver.status_name(result),
                planning_seconds=time.perf_counter() - began,
                diagnostics=["Rolling window has no returned feasible plan; wait"],
            )
        return PlanResult(
            status=solver.status_name(result),
            starts={
                key[0]: [state["time"] + solver.value(starts[key]) * TICK]
                for key in pending
            },
            planning_seconds=time.perf_counter() - began,
            diagnostics=[
                "One pending traversal per robot; active movements frozen",
                f"Exact equal-release clique reductions: {reductions}",
            ],
        )
