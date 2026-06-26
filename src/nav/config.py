"""Tunable parameters for the navigation stack — *only* the ones that vary
per deployment.

If you find yourself wanting to tune a knob that isn't here, it's most likely
an implementation detail (controller gain, sensitivity threshold, telemetry
rate) and lives as a module-private ``_CONSTANT`` inside the relevant nav
module. Add a field here only if it's a value that genuinely changes between
deployments / environments.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavConfig:
    # ── Speed & Steering ────────────────────────────────────────────────
    #: m/s — fallback walking speed when a NavigationSegment doesn't
    #: specify ``max_speed``. Smaller rooms / cautious mode → lower.
    default_speed: float = 1.0

    #: rad/s — hard cap on rotation speed. Hardware-derived safety limit.
    max_angular_velocity: float = 0.8

    # ── Arrival ─────────────────────────────────────────────────────────
    #: m — fallback "close enough to count as reached" tolerance when a
    #: NavigationSegment doesn't specify ``allowed_deviation``. Higher = the
    #: dog stops further from the waypoint. Should match the smallest
    #: ``allowedDeviationXY`` you expect in VDA5050 orders.
    arrival_deviation: float = 0.15

    # ── Safety ──────────────────────────────────────────────────────────
    #: s — how long without movement before declaring BLOCKED. Busy
    #: environments (people in the way) want longer; empty rooms shorter.
    blocked_timeout_sec: float = 5.0

    # ── Pure-Pursuit (used by Slice 4) ──────────────────────────────────
    #: m — how far ahead on the edge the controller aims. Larger = smoother
    #: but more corner-cutting; smaller = tighter line-following but jerkier.
    lookahead_distance: float = 0.8

    #: m — hard cap on how much corner the controller may shave. Must be
    #: ≤ the smallest ``allowedDeviationXY`` you expect, otherwise the AGV
    #: would violate VDA5050 §6.6 deviation guarantees on sharp corners.
    max_lookahead_corner_cut: float = 0.15
