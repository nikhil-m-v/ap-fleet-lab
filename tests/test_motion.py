import math
import numpy as np
import pytest
from ap_fleet.motion import Motion, minimum_separation


def test_triangular_and_trapezoidal_profiles():
    assert Motion([(0, 0), (1, 0)], 10, 1).duration == pytest.approx(2)
    assert Motion([(0, 0), (10, 0)], 2, 1).duration == pytest.approx(7)
    m = Motion([(0, 0), (10, 0)], 2, 1)
    for t in np.linspace(0, m.duration, 100):
        p, v, a = m.state(t)
        assert 0 <= p[0] <= 10 + 1e-8
        assert np.linalg.norm(v) <= 2 + 1e-8
        assert np.linalg.norm(a) <= 1 + 1e-8
    assert np.linalg.norm(m.state(m.duration)[1]) == 0


def test_corners_stop_and_manual_stop_preserves_limits():
    motion = Motion([(0, 0), (3, 0), (3, 4)], 1.5, 1)
    original = motion.duration
    at = motion.add_stop(0.2, 3)
    assert at > 0.2
    assert motion.duration == pytest.approx(original + 3)
    assert np.linalg.norm(motion.state(at + 1)[1]) == 0
    assert motion.state(at + 1)[0] == pytest.approx([3, 0])
    assert motion.state(motion.duration)[0] == pytest.approx([3, 4])


def test_collision_between_endpoints_is_detected():
    horizontal = Motion([(-1, 0), (1, 0)], 10, 10)
    vertical = Motion([(0, -1), (0, 1)], 10, 10)
    assert math.dist(horizontal.state(0)[0], vertical.state(0)[0]) > 1
    assert (
        math.dist(
            horizontal.state(horizontal.duration)[0],
            vertical.state(vertical.duration)[0],
        )
        > 1
    )
    assert (
        minimum_separation((horizontal, 0), (vertical, 0), 0, horizontal.duration)
        < 1e-7
    )


def test_stationary_bay_and_motion_minimum():
    m = Motion([(-2, 0), (2, 0)], 1, 1)
    assert minimum_separation((m, 0), np.array([0, 2]), 0, m.duration) == pytest.approx(
        2
    )
