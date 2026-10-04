import itertools
import math
import pytest
from ap_fleet.models import Scenario, Robot
from ap_fleet.geometry import validate_geometry, incompatibilities
from ap_fleet.scenarios import make_scenario
from ap_fleet.motion import nominal_duration
from ap_fleet.scheduling import PeriodicScheduler, RollingScheduler, ticks, TICK


def test_known_period_and_many_expanded_cycles():
    scenario = make_scenario("intersection", 2)
    conflicts = incompatibilities(scenario)
    plan = PeriodicScheduler(conflicts, margin=0.2).plan(scenario)
    expected = sum(
        (ticks(nominal_duration(r, j)) + 2) * TICK
        for r in scenario.robots
        for j in range(2)
    )
    assert plan.status == "OPTIMAL"
    assert plan.period == pytest.approx(expected)
    assert plan.optimality_gap == 0
    intervals = []
    for r in scenario.robots:
        for j in range(2):
            for n in range(-4, 5):
                start = plan.starts[r.id][j] + n * plan.period
                intervals.append(
                    (
                        (r.id, j),
                        start,
                        start + (ticks(nominal_duration(r, j)) + 2) * TICK,
                    )
                )
    for (a, sa, ea), (b, sb, eb) in itertools.combinations(intervals, 2):
        if frozenset((a, b)) in conflicts:
            assert ea <= sb + 1e-7 or eb <= sa + 1e-7


def test_infeasible_period_limit_and_zero_budget():
    scenario = make_scenario("intersection", 2)
    conflicts = incompatibilities(scenario)
    assert (
        PeriodicScheduler(conflicts, max_period=1).plan(scenario).status == "INFEASIBLE"
    )
    plan = PeriodicScheduler(conflicts, budget=0).plan(scenario)
    assert plan.status == "UNKNOWN" and not plan.starts


def test_rolling_preserves_frozen_occupancy():
    scenario = make_scenario("intersection", 2)
    plan = RollingScheduler(incompatibilities(scenario), margin=0.2).plan(
        scenario, {"time": 10, "pending": [("r01", 0)], "active": [(("r00", 0), 4.2)]}
    )
    assert plan.starts["r01"][0] >= 14.2 - 1e-8


@pytest.mark.parametrize("kind", ["intersection", "corridor", "warehouse"])
@pytest.mark.parametrize("fleet", [4, 8, 16, 32])
def test_all_generated_private_bays(kind, fleet):
    assert len(validate_geometry(make_scenario(kind, fleet)).robots) == fleet


def test_invalid_waiting_bay_and_noncyclic_route():
    with pytest.raises(ValueError):
        Robot(id="bad", legs=[[(0, 0), (1, 0)]])
    scenario = Scenario(
        name="bad bays",
        robots=[
            Robot(id="a", legs=[[(-2, 0), (0, 0)], [(0, 0), (-2, 0)]]),
            Robot(id="b", legs=[[(0, -2), (0, 2)], [(0, 2), (0, -2)]]),
        ],
    )
    with pytest.raises(ValueError, match="Private bay"):
        validate_geometry(scenario)


def test_rolling_clique_reduction_matches_exhaustive_weighted_optimum():
    scenario = make_scenario("intersection", 3)
    for index, robot in enumerate(scenario.robots):
        robot.max_speed = 0.8 + index * 0.3
    pending = [(r.id, 0) for r in scenario.robots]
    durations = {
        key: ticks(nominal_duration(scenario.robots[i], 0)) + 2
        for i, key in enumerate(pending)
    }
    weights = {key: len(pending) - i for i, key in enumerate(pending)}
    scores = []
    for order in itertools.permutations(pending):
        at, score = 0, 0
        for key in order:
            score += weights[key] * at
            at += durations[key]
        scores.append(score)
    plan = RollingScheduler(incompatibilities(scenario)).plan(
        scenario, {"time": 0, "pending": pending, "active": []}
    )
    assert plan.status == "OPTIMAL"
    score = sum(weights[key] * round(plan.starts[key[0]][0] / TICK) for key in pending)
    assert score == min(scores)


@pytest.mark.parametrize("kind", ["intersection", "corridor", "warehouse"])
def test_large_fleet_constructive_period_is_certified(kind):
    scenario = make_scenario(kind, 32)
    plan = PeriodicScheduler(incompatibilities(scenario), budget=2).plan(scenario)
    assert plan.status == "OPTIMAL"
    assert plan.period == pytest.approx(plan.lower_bound)
    assert plan.optimality_gap == 0
