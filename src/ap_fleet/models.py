from typing import Literal
from pydantic import BaseModel, Field, model_validator
import math

Point = tuple[float, float]


class Robot(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    radius: float = Field(default=0.18, gt=0, le=2)
    max_speed: float = Field(default=1.5, gt=0, le=10)
    acceleration: float = Field(default=1.0, gt=0, le=10)
    legs: list[list[Point]] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def route(self):
        for i, leg in enumerate(self.legs):
            if len(leg) < 2 or len(leg) > 100:
                raise ValueError("Each leg needs 2–100 points")
            if any(not math.isfinite(v) or abs(v) > 10000 for p in leg for v in p):
                raise ValueError("Coordinates must be finite and within 10 km")
            if any(math.dist(a, b) < 1e-6 for a, b in zip(leg, leg[1:])):
                raise ValueError("Consecutive points must differ")
            if math.dist(leg[-1], self.legs[(i + 1) % len(self.legs)][0]) > 1e-6:
                raise ValueError("Legs must join into a closed cyclic route")
        return self


class Scenario(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    robots: list[Robot] = Field(min_length=1, max_length=32)
    clearance: float = Field(default=0.08, ge=0, le=2)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({r.id for r in self.robots}) != len(self.robots):
            raise ValueError("Robot IDs must be unique")
        return self


class RunConfig(BaseModel):
    scenario: Literal["intersection", "corridor", "warehouse"] = "intersection"
    custom_scenario: Scenario | None = None
    fleet_size: int = Field(default=4, ge=2, le=32)
    algorithm: Literal["fcfs", "periodic", "rolling"] = "periodic"
    demand: Literal["saturated", "intermittent", "bursts"] = "saturated"
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    duration: float = Field(default=120, gt=0, le=3600)
    warmup: float = Field(default=0, ge=0, le=3600)
    delay_probability: float = Field(default=0.15, ge=0, le=1)
    max_delay: float = Field(default=3, ge=0, le=60)
    slowdown_probability: float = Field(default=0.1, ge=0, le=1)
    slowdown_factor: float = Field(default=0.6, gt=0, le=1)
    timing_margin: float = Field(default=0.2, ge=0, le=10)
    solver_budget: float = Field(default=2, ge=0, le=30)
    playback_speed: float = Field(default=10, gt=0, le=100)


class PlanResult(BaseModel):
    status: str
    starts: dict[str, list[float]] = Field(default_factory=dict)
    period: float | None = None
    lower_bound: float | None = None
    optimality_gap: float | None = None
    planning_seconds: float = 0
    diagnostics: list[str] = Field(default_factory=list)
