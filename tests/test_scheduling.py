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
