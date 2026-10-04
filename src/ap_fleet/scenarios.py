import math
from .models import Robot, Scenario
from .geometry import validate_geometry


def make_scenario(kind="intersection", fleet_size=4):
    if (
        kind not in ("intersection", "corridor", "warehouse")
        or not 2 <= fleet_size <= 32
    ):
        raise ValueError("Unknown scenario or unsupported fleet size")
    robots = []
    radius = max(6.0, fleet_size * 0.8)
    for i in range(fleet_size):
        angle = math.pi * i / fleet_size + math.pi / (2 * fleet_size)
        a = (radius * math.cos(angle), radius * math.sin(angle))
        b = (-a[0], -a[1])
        if kind == "corridor":
            y = (i - (fleet_size - 1) / 2) * 1.1
            a, b = (-radius, y), (radius, y)
            route = [a, (-1.0, 0.0), (1.0, 0.0), b]
        elif kind == "warehouse":
            # Two independent workcells with different route lengths, exercising
            # concurrency and common-period underutilization, not only one clique.
            count = (fleet_size + 1) // 2
            lane_radius = max(6.0, count * 0.8) + (2 if i % 2 else 0)
            cx = (max(6.0, count * 0.8) + 6) * (1 if i % 2 else -1)
            theta = math.pi * ((i // 2) + 0.5) / count
            a = (cx + lane_radius * math.cos(theta), lane_radius * math.sin(theta))
            b = (cx - lane_radius * math.cos(theta), -lane_radius * math.sin(theta))
            route = [a, (cx, 1.0), (cx, -1.0), b]
        else:
            route = [a, b]
        robots.append(Robot(id=f"r{i:02d}", legs=[route, list(reversed(route))]))
    return validate_geometry(Scenario(name=kind, robots=robots))
