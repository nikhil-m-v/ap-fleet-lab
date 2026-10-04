import math
from .models import Scenario


def point_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(
        0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy))
    )
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def segment_distance(a, b, c, d):
    # Strict crossing plus endpoint distances also handles collinear segments.
    if cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0:
        return 0.0
    return min(
        point_segment(a, c, d),
        point_segment(b, c, d),
        point_segment(c, a, b),
        point_segment(d, a, b),
    )


def path_distance(first, second):
    return min(
        segment_distance(a, b, c, d)
        for a, b in zip(first, first[1:])
        for c, d in zip(second, second[1:])
    )


def validate_geometry(scenario: Scenario):
    for robot in scenario.robots:
        for bay in {tuple(leg[0]) for leg in robot.legs}:
            for other in scenario.robots:
                if other.id == robot.id:
                    continue
                threshold = robot.radius + other.radius + scenario.clearance
                if any(
                    point_segment(bay, a, b) < threshold - 1e-9
                    for leg in other.legs
                    for a, b in zip(leg, leg[1:])
                ):
                    raise ValueError(
                        f"Private bay for {robot.id} intersects swept route of {other.id}"
                    )
    return scenario


def incompatibilities(scenario):
    conflicts = set()
    for i, robot in enumerate(scenario.robots):
        for other in scenario.robots[i + 1 :]:
            for j, first in enumerate(robot.legs):
                for k, second in enumerate(other.legs):
                    if (
                        path_distance(first, second)
                        < robot.radius + other.radius + scenario.clearance + 1e-9
                    ):
                        conflicts.add(frozenset(((robot.id, j), (other.id, k))))
    return conflicts
