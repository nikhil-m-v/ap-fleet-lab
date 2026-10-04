from dataclasses import dataclass
import math
import numpy as np


@dataclass
class Phase:
    start: float
    duration: float
    p: np.ndarray
    v: np.ndarray
    a: np.ndarray

    def state(self, time):
        t = min(self.duration, max(0.0, time - self.start))
        return self.p + self.v * t + self.a * t * t / 2, self.v + self.a * t, self.a


class Motion:
    def __init__(self, points, speed, acceleration, stop=0.0):
        points = [np.array(p, dtype=float) for p in points]
        if stop:
            points.insert(1, (points[0] + points[1]) / 2)
        self.phases = []
        self.duration = 0.0
        self.end = points[-1]
        self.stops = []
        for index, (a, b) in enumerate(zip(points, points[1:])):
            length = float(np.linalg.norm(b - a))
            direction = (b - a) / length
            peak = min(speed, math.sqrt(length * acceleration))
            accel_time = peak / acceleration
            cruise_time = max(0.0, (length - peak * peak / acceleration) / peak)
            current = a.copy()
            for duration, velocity, acc in (
                (accel_time, 0.0, acceleration),
                (cruise_time, peak, 0.0),
                (accel_time, peak, -acceleration),
            ):
                if duration < 1e-12:
                    continue
                phase = Phase(
                    self.duration,
                    duration,
                    current.copy(),
                    direction * velocity,
                    direction * acc,
                )
                self.phases.append(phase)
                current = phase.state(self.duration + duration)[0]
                self.duration += duration
            self.stops.append(self.duration)
            if stop and index == 0:
                self.phases.append(
                    Phase(self.duration, stop, b.copy(), np.zeros(2), np.zeros(2))
                )
                self.duration += stop

    def state(self, time):
        if time >= self.duration - 1e-10:
            return self.end.copy(), np.zeros(2), np.zeros(2)
        for phase in self.phases:
            if time < phase.start + phase.duration - 1e-10:
                return phase.state(time)
        return self.end.copy(), np.zeros(2), np.zeros(2)

    def add_stop(self, time, seconds):
        # Stop at the next existing zero-speed waypoint, preserving acceleration bounds.
        at = next((t for t in self.stops if t >= time - 1e-9), self.duration)
        p = self.state(at)[0]
        for phase in self.phases:
            if phase.start >= at - 1e-9:
                phase.start += seconds
        self.phases.append(Phase(at, seconds, p, np.zeros(2), np.zeros(2)))
        self.phases.sort(key=lambda phase: phase.start)
        self.stops = [t + seconds if t >= at else t for t in self.stops]
        self.duration += seconds
        return at


def nominal_duration(robot, leg):
    return Motion(robot.legs[leg], robot.max_speed, robot.acceleration).duration


def minimum_separation(first, second, start, end):
    """Exact minimum of piecewise quadratic relative motion (cubic stationary roots).

    Arguments are (motion, absolute_start) or a stationary 2D position.
    """

    def state(obj, time):
        return (
            obj[0].state(time - obj[1])
            if isinstance(obj, tuple)
            else (np.asarray(obj), np.zeros(2), np.zeros(2))
        )

    breaks = {start, end}
    for obj in (first, second):
        if isinstance(obj, tuple):
            for phase in obj[0].phases:
                for time in (
                    phase.start + obj[1],
                    phase.start + phase.duration + obj[1],
                ):
                    if start < time < end:
                        breaks.add(time)
    best = math.inf
    times = sorted(breaks)
    for lo, hi in zip(times, times[1:]):
        p1, v1, a1 = state(first, lo + 1e-10)
        p2, v2, a2 = state(second, lo + 1e-10)
        r, v, a = p1 - p2, v1 - v2, a1 - a2
        coefficients = [
            2 * np.dot(r, v),
            2 * (np.dot(v, v) + np.dot(r, a)),
            3 * np.dot(v, a),
            np.dot(a, a),
        ]
        while len(coefficients) > 1 and abs(coefficients[-1]) < 1e-12:
            coefficients.pop()
        roots = (
            np.polynomial.polynomial.polyroots(coefficients)
            if len(coefficients) > 1
            else []
        )
        candidates = [0.0, hi - lo] + [
            float(z.real)
            for z in roots
            if abs(z.imag) < 1e-7 and 0 <= z.real <= hi - lo
        ]
        best = min(
            best,
            *(float(np.linalg.norm(r + v * t + a * t * t / 2)) for t in candidates),
        )
    return best
