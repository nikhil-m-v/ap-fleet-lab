import pytest
from ap_fleet.models import RunConfig
from ap_fleet.simulation import Simulation, indexed_random
from ap_fleet.cli import execute
from ap_fleet.storage import read_replay


@pytest.mark.parametrize("algorithm", ["fcfs", "periodic", "rolling"])
@pytest.mark.parametrize("demand", ["saturated", "intermittent", "bursts"])
def test_delayed_execution_and_demand(algorithm, demand):
    sim = Simulation(
        RunConfig(
            algorithm=algorithm,
            demand=demand,
            fleet_size=2,
            duration=60,
            delay_probability=1,
            max_delay=5,
            slowdown_probability=1,
        )
    )
    result = sim.finish()
    assert result["status"] == "completed"
    assert result["metrics"]["clearance_violations"] == 0
    assert result["metrics"]["completed_missions"] > 0
    assert all(
        e["end"] > e["start"] for e in sim.events if e["type"] == "movement_start"
    )


def test_permissions_do_not_expire_at_nominal_end():
    sim = Simulation(
        RunConfig(
            algorithm="fcfs",
            fleet_size=2,
            duration=80,
            delay_probability=0,
            slowdown_probability=0,
        )
    )
    sim.step()
    first = sim.states["r00"]
    nominal_end = first.started + first.motion.duration
    sim.inject("r00", 20)
    while sim.time < nominal_end + 5:
        sim.step()
    assert first.motion is not None
    assert sim.states["r01"].motion is None
    assert sim.finish()["metrics"]["clearance_violations"] == 0


def test_deterministic_randomness_and_headless_runs():
    assert (
        indexed_random(3, "r00", 2, 1, "stop").random()
        == indexed_random(3, "r00", 2, 1, "stop").random()
    )
    config = RunConfig(algorithm="fcfs", duration=60, fleet_size=2, seed=17)
    a, b = Simulation(config), Simulation(config)
    a.finish()
    b.finish()
    assert a.events == b.events
    assert a.metrics() == b.metrics()


def test_timeout_keeps_robots_at_bays():
    sim = Simulation(RunConfig(algorithm="periodic", solver_budget=0))
    assert sim.status == "planning_failed"
    assert not any(s.motion for s in sim.states.values())


def test_replay_terminal_state_matches_headless(tmp_path):
    file = tmp_path / "replay.jsonl.gz"
    result = execute(RunConfig(algorithm="fcfs", duration=20, fleet_size=2), file)
    replay = read_replay(file)
    assert replay["frames"][-1]["metrics"] == result["metrics"]
    assert replay["frames"][-1]["status"] == result["status"]
    assert replay["events"][-1]["time"] <= 20 + 1e-7


def test_unavailable_mission_slots_do_not_spawn_extra_robots():
    sim = Simulation(
        RunConfig(
            algorithm="periodic", demand="intermittent", duration=120, fleet_size=2
        )
    )
    sim.finish()
    assert len(sim.states) == 2
    assert all(s.mission <= len(s.arrivals) for s in sim.states.values())


@pytest.mark.parametrize("algorithm", ["fcfs", "periodic", "rolling"])
def test_cooldown_cannot_be_bypassed_by_immediate_self_reacquisition(algorithm):
    sim = Simulation(
        RunConfig(
            algorithm=algorithm,
            fleet_size=4,
            duration=100,
            delay_probability=0,
            slowdown_probability=0,
        )
    )
    sim.finish()
    assert min(sim.metrics()["per_robot_completions"].values()) >= 1
    assert sim.metrics()["jain_fairness"] > 0.8
