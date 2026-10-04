from dataclasses import dataclass, field
import hashlib
import math
import random
import time
import numpy as np
from .models import RunConfig
from .geometry import incompatibilities, validate_geometry
from .motion import Motion, nominal_duration, minimum_separation
from .scenarios import make_scenario
from .scheduling import FCFSScheduler, PeriodicScheduler, RollingScheduler


def indexed_random(seed, robot, mission, leg, kind):
    digest = hashlib.sha256(f"{seed}|{robot}|{mission}|{leg}|{kind}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


@dataclass
class Runtime:
    robot: object
    position: np.ndarray
    leg: int = 0
    mission: int = 0
    ready_since: float = 0
    cycle: int | None = None
    motion: Motion | None = None
    started: float = 0
    completions: list[float] = field(default_factory=list)
    arrivals: list[float] = field(default_factory=list)
    manual_stops: list[float] = field(default_factory=list)
    disruption_end: float | None = None
    flagged: bool = False


class Simulation:
    def __init__(self, config: RunConfig):
        self.config = config
        self.scenario = validate_geometry(
            config.custom_scenario or make_scenario(config.scenario, config.fleet_size)
        )
        self.conflicts = incompatibilities(self.scenario)
        self.scheduler = {
            "fcfs": FCFSScheduler,
            "periodic": PeriodicScheduler,
            "rolling": RollingScheduler,
        }[config.algorithm](
            **(
                {}
                if config.algorithm == "fcfs"
                else {
                    "conflicts": self.conflicts,
                    "margin": config.timing_margin,
                    "budget": config.solver_budget,
                }
            )
        )
        self.plan = self.scheduler.plan(self.scenario)
        self.status = "running"
        if config.algorithm == "periodic" and not self.plan.starts:
            self.status = "planning_failed"
        self.time = 0.0
        self.total = config.warmup + config.duration
        self.events = []
        self.waits = []
        self.recovery = []
        self.clearance_violations = 0
        self.minimum_clearance = None
        self.cooldowns = []
        self.planning_times = (
            [self.plan.planning_seconds] if config.algorithm != "fcfs" else []
        )
        self.planning_statuses = [self.plan.status]
        self.rolling_signature = None
        self.rolling_due = {}
        self.schedule_version = 1
        self.queue_at_warmup = None
        self.completed_since_progress = 0.0
        self.states = {}
        for robot in self.scenario.robots:
            state = Runtime(
                robot=robot, position=np.array(robot.legs[0][0], dtype=float)
            )
            if config.demand != "saturated":
                nominal = sum(
                    nominal_duration(robot, j) for j in range(len(robot.legs))
                )
                rng = indexed_random(config.seed, robot.id, 0, 0, "demand")
                if config.demand == "intermittent":
                    arrival = 0.0
                    while arrival < self.total:
                        state.arrivals.append(arrival)
                        arrival += rng.expovariate(1 / max(1.0, nominal * 1.5))
                else:
                    for burst in np.arange(0, self.total, 30.0):
                        state.arrivals.extend([float(burst)] * rng.randint(1, 3))
            self.states[robot.id] = state
        self.emit("plan", plan=self.plan.model_dump(), version=self.schedule_version)

    def emit(self, kind, **values):
        self.events.append({"time": round(self.time, 6), "type": kind, **values})

    def arrival(self, state):
        if self.config.demand == "saturated":
            return state.ready_since
        return (
            state.arrivals[state.mission]
            if state.mission < len(state.arrivals)
            else math.inf
        )

    def pending(self):
        result = []
        for state in self.states.values():
            if state.motion is None and (
                state.leg > 0 or self.arrival(state) <= self.time + 1e-8
            ):
                if state.leg == 0:
                    state.ready_since = max(state.ready_since, self.arrival(state))
                result.append(state)
        return sorted(result, key=lambda s: (s.ready_since, s.robot.id))

    def queue_size(self):
        if self.config.demand == "saturated":
            return sum(s.motion is None and s.leg == 0 for s in self.states.values())
        return sum(
            max(
                0,
                sum(t <= self.time + 1e-8 for t in s.arrivals)
                - s.mission
                - (1 if s.leg > 0 or s.motion else 0),
            )
            for s in self.states.values()
        )

    def compatible(self, state):
        key = state.robot.id, state.leg
        for other in self.states.values():
            if (
                other.motion
                and frozenset((key, (other.robot.id, other.leg))) in self.conflicts
            ):
                return False
        return not any(
            until > self.time + 1e-8
            and (key[0] == frozen[0] or frozenset((key, frozen)) in self.conflicts)
            for frozen, until in self.cooldowns
        )

    def due(self, state):
        if self.config.algorithm == "fcfs":
            return state.ready_since
        if self.config.algorithm == "rolling":
            return self.rolling_due.get(state.robot.id, math.inf)
        starts = self.plan.starts[state.robot.id]
        period = self.plan.period
        if state.cycle is None:
            state.cycle = max(
                0, math.ceil((state.ready_since - starts[0] - 1e-8) / period)
            )
        due = starts[state.leg] + state.cycle * period
        if state.leg == 0 and self.time >= due + period - 1e-8:
            skipped = max(1, math.floor((self.time - due + 1e-8) / period))
            state.cycle += skipped
            self.emit("missed_slot", robot=state.robot.id, count=skipped)
            due += skipped * period
        return due

    def refresh_rolling(self, pending):
        signature = (
            tuple((s.robot.id, s.leg, s.mission) for s in pending),
            tuple(
                (s.robot.id, s.leg, s.started, s.motion.duration)
                for s in self.states.values()
                if s.motion
            ),
        )
        if signature == self.rolling_signature:
            return
        self.rolling_signature = signature
        active = [
            (
                (s.robot.id, s.leg),
                max(0.0, s.started + s.motion.duration - self.time)
                + self.config.timing_margin,
            )
            for s in self.states.values()
            if s.motion
        ]
        active.extend(
            (key, until - self.time)
            for key, until in self.cooldowns
            if until > self.time + 1e-8
        )
        plan = self.scheduler.plan(
            self.scenario,
            {
                "pending": [(s.robot.id, s.leg) for s in pending],
                "active": active,
                "time": self.time,
            },
        )
        self.plan = plan
        self.planning_times.append(plan.planning_seconds)
        self.planning_statuses.append(plan.status)
        self.rolling_due = {key: value[0] for key, value in plan.starts.items()}
        self.schedule_version += 1
        self.emit("plan", plan=plan.model_dump(), version=self.schedule_version)
        if pending and plan.status not in ("OPTIMAL", "FEASIBLE"):
            self.emit("solver_wait", status=plan.status)

    def dispatch(self):
        pending = self.pending()
        if self.config.algorithm == "rolling":
            self.refresh_rolling(pending)
        for state in sorted(pending, key=lambda s: (self.due(s), s.robot.id)):
            due = self.due(state)
            if due > self.time + 1e-8 or not self.compatible(state):
                if self.time - state.ready_since > 60 and not state.flagged:
                    self.emit(
                        "starvation_observed",
                        robot=state.robot.id,
                        wait=self.time - state.ready_since,
                    )
                    state.flagged = True
                continue
            robot = state.robot
            rng_stop = indexed_random(
                self.config.seed, robot.id, state.mission, state.leg, "stop"
            )
            stop = (
                rng_stop.uniform(0, self.config.max_delay)
                if rng_stop.random() < self.config.delay_probability
                else 0.0
            )
            if state.manual_stops:
                stop += sum(state.manual_stops)
                state.manual_stops.clear()
            rng_speed = indexed_random(
                self.config.seed, robot.id, state.mission, state.leg, "speed"
            )
            speed = robot.max_speed * (
                self.config.slowdown_factor
                if rng_speed.random() < self.config.slowdown_probability
                else 1.0
            )
            state.motion = Motion(
                robot.legs[state.leg], speed, robot.acceleration, stop
            )
            state.started = self.time
            if self.time >= self.config.warmup:
                self.waits.append(max(0.0, self.time - state.ready_since))
            state.flagged = False
            if stop:
                dwell = next(
                    p
                    for p in state.motion.phases
                    if np.linalg.norm(p.v) < 1e-12 and np.linalg.norm(p.a) < 1e-12
                )
                state.disruption_end = self.time + dwell.start + dwell.duration
            self.emit(
                "movement_start",
                robot=robot.id,
                leg=state.leg,
                mission=state.mission,
                planned=due,
                start=self.time,
                end=self.time + state.motion.duration,
                stop=stop,
                speed=speed,
                version=self.schedule_version,
            )

    def inject(self, robot, seconds):
        if robot not in self.states or not 0 < seconds <= 60:
            raise ValueError("Unknown robot or stop outside (0,60] seconds")
        state = self.states[robot]
        if state.motion:
            at = state.motion.add_stop(self.time - state.started, seconds)
            state.disruption_end = state.started + at + seconds
            effective = state.started + at
        else:
            state.manual_stops.append(seconds)
            effective = None
        self.emit(
            "manual_disruption", robot=robot, seconds=seconds, effective_at=effective
        )
        self.rolling_signature = None

    def check_clearance(self, target):
        states = list(self.states.values())
        poses = [
            s.motion.state(self.time - s.started)[0] if s.motion else s.position
            for s in states
        ]
        positions = np.asarray(poses)
        radii = np.array([s.robot.radius for s in states])
        speeds = np.array([s.robot.max_speed for s in states])
        distances = np.linalg.norm(
            positions[:, None, :] - positions[None, :, :], axis=2
        )
        thresholds = radii[:, None] + radii[None, :] + self.scenario.clearance
        approaches = (speeds[:, None] + speeds[None, :]) * (target - self.time)
        # Vectorized, independent speed-bound broad phase. No reservation graph.
        for i, j in np.argwhere(
            np.triu(distances <= thresholds + approaches + 1e-8, k=1)
        ):
            first, second = states[i], states[j]
            threshold = thresholds[i, j]
            a = (first.motion, first.started) if first.motion else first.position
            b = (second.motion, second.started) if second.motion else second.position
            separation = minimum_separation(a, b, self.time, target)
            gap = separation - first.robot.radius - second.robot.radius
            self.minimum_clearance = (
                gap
                if self.minimum_clearance is None
                else min(self.minimum_clearance, gap)
            )
            if separation < threshold - 1e-7:
                self.clearance_violations += 1
                self.status = "failed"
                self.emit(
                    "clearance_violation",
                    robots=[first.robot.id, second.robot.id],
                    separation=separation,
                    required=threshold,
                    interval=[self.time, target],
                )
                return False
        return True

    def step(self):
        if self.status != "running":
            return False
        self.cooldowns = [
            (key, until) for key, until in self.cooldowns if until > self.time + 1e-8
        ]
        if self.queue_at_warmup is None and self.time >= self.config.warmup - 1e-8:
            self.queue_at_warmup = self.queue_size()
        self.dispatch()
        target = min(self.time + 0.1, self.total)
        for state in self.states.values():
            if state.motion:
                target = min(target, state.started + state.motion.duration)
        if self.time < self.config.warmup < target:
            target = self.config.warmup
        if not self.check_clearance(target):
            return False
        self.time = target
        for state in self.states.values():
            if (
                state.motion
                and state.started + state.motion.duration <= self.time + 1e-8
            ):
                state.position = state.motion.end.copy()
                self.cooldowns.append(
                    ((state.robot.id, state.leg), self.time + self.config.timing_margin)
                )
                self.emit(
                    "movement_end",
                    robot=state.robot.id,
                    leg=state.leg,
                    mission=state.mission,
                )
                state.motion = None
                state.leg += 1
                state.ready_since = self.time
                if state.leg == len(state.robot.legs):
                    state.leg = 0
                    state.mission += 1
                    state.cycle = None
                    state.completions.append(self.time)
                    self.completed_since_progress = self.time
                    if (
                        state.disruption_end is not None
                        and self.time >= self.config.warmup
                    ):
                        self.recovery.append(max(0.0, self.time - state.disruption_end))
                    state.disruption_end = None
                    self.emit(
                        "mission_complete", robot=state.robot.id, mission=state.mission
                    )
        if self.time >= self.total - 1e-8:
            self.status = "completed"
        return self.status == "running"

    def metrics(self):
        measured = max(0.0, min(self.time, self.total) - self.config.warmup)
        per_robot = {
            s.robot.id: sum(t >= self.config.warmup - 1e-8 for t in s.completions)
            for s in self.states.values()
        }
        completed = sum(per_robot.values())
        counts = np.array(list(per_robot.values()), dtype=float)
        fairness = (
            float(counts.sum() ** 2 / (len(counts) * np.dot(counts, counts)))
            if np.any(counts)
            else None
        )
        return {
            "completed_missions": completed,
            "missions_per_minute": completed * 60 / measured if measured else 0.0,
            "per_robot_completions": per_robot,
            "jain_fairness": fairness,
            "mean_wait_seconds": float(np.mean(self.waits)) if self.waits else 0.0,
            "p95_wait_seconds": (
                float(np.percentile(self.waits, 95)) if self.waits else 0.0
            ),
            "queue_size": self.queue_size(),
            "queue_growth": self.queue_size() - (self.queue_at_warmup or 0),
            "clearance_violations": self.clearance_violations,
            "minimum_checked_clearance": self.minimum_clearance,
            "planning_seconds": sum(self.planning_times),
            "p95_planning_seconds": (
                float(np.percentile(self.planning_times, 95))
                if self.planning_times
                else 0.0
            ),
            "solver_calls": len(self.planning_times),
            "solver_failures": (
                sum(
                    s not in ("OPTIMAL", "FEASIBLE", "IDLE")
                    for s in self.planning_statuses
                )
                if self.config.algorithm != "fcfs"
                else 0
            ),
            "mean_mission_recovery_seconds": (
                float(np.mean(self.recovery)) if self.recovery else None
            ),
            "starvation_events": sum(
                e["type"] == "starvation_observed" for e in self.events
            ),
            "temporary_blocking": any(s.motion is None for s in self.pending()),
            "deadlock_events": 0,
            "measured_seconds": measured,
        }

    def snapshot(self):
        robots = []
        for state in self.states.values():
            position = (
                state.motion.state(self.time - state.started)[0]
                if state.motion
                else state.position
            )
            robots.append(
                {
                    "id": state.robot.id,
                    "position": position.tolist(),
                    "radius": state.robot.radius,
                    "leg": state.leg,
                    "mission": state.mission,
                    "moving": state.motion is not None,
                }
            )
        return {
            "time": self.time,
            "status": self.status,
            "robots": robots,
            "metrics": self.metrics(),
            "plan": self.plan.model_dump(),
            "schedule_version": self.schedule_version,
        }

    def finish(self):
        while self.step():
            pass
        return self.snapshot()
