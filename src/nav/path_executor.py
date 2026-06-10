"""Pure-Pursuit path executor.

Drives toward a *lookahead* point on the polyline `[start_pose, w0, w1, …, wN]`
instead of the next waypoint directly. This gives smooth, continuous cornering
through pass-through waypoints (``must_stop=False``) — the dog arcs around them
instead of stop-and-turn.

State machine
-------------
- ``IDLE``           — no path set.
- ``FOLLOWING``      — actively driving along the polyline.
- ``ARRIVED_SEGMENT``— passed a segment boundary. For ``must_stop=True`` the
  dog is physically stopped and aligned; for ``must_stop=False`` velocity stays
  smooth (the controller is already steering toward the next segment's
  lookahead). ``nav_manager`` calls ``continue_to_next()`` to advance.
- ``ARRIVED_FINAL``  — passed the last waypoint and aligned to its orientation.
- ``BLOCKED``        — no progress for ``blocked_timeout_sec``.

Lookahead geometry
------------------
Lookahead distance is ``NavConfig.lookahead_distance``. The carrot walks
*continuously* through pass-through corners — no hard clamp — so the visual
lookahead glides smoothly from one segment into the next rather than pausing
at the corner and then jumping. To tighten cornering reduce
``NavConfig.lookahead_distance``; the actual deviation from the polyline
corner is bounded by L and the dog's turning radius, not by an analytical
formula.

Within ``_TERMINAL_APPROACH_DISTANCE`` of a ``must_stop`` waypoint a simple
turn-then-drive controller takes over from Pure-Pursuit so the dog reliably
crosses ``allowed_deviation`` instead of wobbling around the goal.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from loguru import logger

from interfaces.motion import MovementCommand, MovementSource
from interfaces.navigation import (
    NavigationState,
    NavigationStatus,
    PathWaypoint,
    PlannedPath,
    Pose2D,
    normalize_angle,
)
from nav.config import NavConfig
from nav.utils import clamp


# ── Internal tuning constants — intentionally NOT in NavConfig ─────────────
_ANGULAR_KP: float = 1.5           # rad/s per rad of heading error
_ORIENTATION_KP: float = 1.2       # rad/s per rad of orientation error (align phase)
_STATUS_INTERVAL_SEC: float = 0.5  # FOLLOWING status republish rate
_BLOCKED_DISTANCE_THRESHOLD: float = 0.05
_BLOCKED_ANGLE_THRESHOLD: float = math.radians(5)
#: Distance from a must_stop waypoint at which Pure-Pursuit hands over to a
#: simple turn-then-drive controller. Pure-Pursuit's lookahead-to-target
#: geometry gets unusable near the goal — bearing jitters with sub-cm pose
#: changes and the dog wobbles around the waypoint without ever crossing
#: allowed_deviation. The terminal controller fixes that with explicit
#: rotate-in-place / drive-straight phases.
_TERMINAL_APPROACH_DISTANCE: float = 0.8
#: Within this distance to a must_stop the terminal step linearly ramps speed
#: down from ``wp.speed`` to ``_TERMINAL_BRAKE_FLOOR_SPEED``. Without the
#: ramp the Go2 hits align at full cruise momentum and the legs drift the
#: body 10-30 cm past the target during the in-place rotation. Symmetric to
#: ``_WARMUP_DISTANCE`` on the other side of a must_stop.
_TERMINAL_BRAKE_DISTANCE: float = 0.5
#: Absolute floor on the brake-ramped approach speed. Picked above the gait
#: minimum (~0.2 m/s observed) so the legs keep walking — going lower
#: silently stalls the gait and the dog never crosses ``allowed_deviation``.
_TERMINAL_BRAKE_FLOOR_SPEED: float = 0.25
#: BLOCKED suppression zone for must_stop convergence. Matches the terminal
#: approach distance so the rotate-in-place phase isn't aborted when the
#: hardware turns slower than commanded.
_CONVERGENCE_ZONE: float = _TERMINAL_APPROACH_DISTANCE
#: Seconds the executor lingers in ``ARRIVED_SEGMENT`` for a ``must_stop``
#: intermediate before letting ``continue_to_next()`` advance to the next
#: segment. Without the dwell, NavManager's per-tick auto-continue advances
#: ~67 ms after arrival and the visible brake-and-go looks like one
#: continuous motion. The dwell forces a visible pause so operators can
#: confirm sharp corners actually stopped. Final-target ARRIVED_FINAL is
#: not affected — there's no next segment to advance to.
_MUST_STOP_DWELL_SEC: float = 0.5
#: Heading error above which the executor rotates in place at the *start* of
#: a fresh path before letting Pure-Pursuit drive. Without this, starting
#: with the lookahead far off to the side produces a sideways slide instead
#: of a clean turn-then-drive. Applied once per ``set_path``; in-flight
#: drift is handled by Pure-Pursuit's cos-scaled ``vx`` directly.
_INITIAL_TURN_THRESHOLD: float = math.radians(20)
#: Below this upcoming-turn angle no anticipation kicks in — the lookahead
#: uses the default ``NavConfig.lookahead_distance`` for a near-straight
#: continuation.
_ANTICIPATE_ANGLE_MIN: float = math.radians(30)
#: At and above this turn angle the lookahead reaches its full anticipation
#: multiplier. Picked just under the sharp-turn threshold the bridge uses
#: for must_stop promotion — anything sharper is handled by stop-and-align
#: instead of arc-cornering.
_ANTICIPATE_ANGLE_FULL: float = math.radians(80)
#: Multiplier on the default lookahead at sharp pass-through corners (reached
#: at and above ``_ANTICIPATE_ANGLE_FULL``).
#:
#: > 1.0 → carrot transitions onto the next segment sooner, dog starts arcing
#:         earlier, wider/smoother curve (more corner-cutting).
#: < 1.0 → carrot stays closer to the dog, tighter path-following, less
#:         corner-cutting (good when the gait can't cleanly track a wide arc).
#:
#: Empirically tune against the actual robot — for the Go2 values around
#: 0.6-1.0 work best, depending on how much you trade smoothness vs precision.
_ANTICIPATE_MAX_FACTOR: float = 0.6
#: Minimum upcoming-turn angle for the r-trigger pass-through advance. Below
#: this we keep the projection-only advance so near-straight pass-through
#: waypoints get traversed precisely (VDA5050's lastNodeId stays accurate).
#: Above this the smoothness payoff of cutting the last r metres outweighs
#: the precision cost — the dog arcs into the next segment earlier.
_R_TRIGGER_TURN_THRESHOLD: float = math.radians(80)
#: Fraction of ``allowed_deviation`` at which the must_stop align step fires.
#: Without this the dog parks at the *boundary* of the deviation circle it
#: first entered — visually as if it stops too early, off-center. Halving
#: the trigger drives the dog further toward the actual waypoint before
#: switching to in-place rotation. Still spec-compliant: VDA5050 says
#: "reached when within allowed_deviation"; closer is fine.
_ALIGN_TRIGGER_FACTOR: float = 0.5
#: Heading-error threshold above which Pure-Pursuit floors ``vx`` instead of
#: clamping it to zero. The cos-clamp at ±90° is a stall trap: the dog
#: rotates in place, but if real-world rotation is slower than commanded the
#: pose doesn't update enough to cross either the projection trigger (t≥1)
#: or the r-trigger circle — dog and lookahead both freeze.
_STALL_PREVENTION_ANGLE: float = math.radians(80)
#: Minimum ``vx`` when stall prevention kicks in. Above the Go2 gait minimum
#: (~0.2 m/s) so the legs actually walk; commanding less stalls silently.
_STALL_PREVENTION_FLOOR: float = 0.25
#: Maximum ticks (at 15Hz nav loop) the dog may spend with heading_error
#: above the stall threshold on a pass-through corner before the executor
#: gives up and force-advances to the next segment. Prevents a chase-the-
#: bearing loop where real-world rotation is slower than commanded and the
#: dog ends up doing a full 360° trying to catch up to a moving lookahead.
#: 45 ticks ≈ 3 s — enough for a legit sharp turn, well under a full spin.
_STALL_TICK_LIMIT: int = 45
#: Distance from a sharp pass-through corner at which the velocity starts
#: ramping down. Slower approach = tighter trajectory = less corner-cutting
#: = dog tracks closer to the actual waypoint, doesn't end up off-path in
#: a stall configuration.
_CORNER_SLOWDOWN_DISTANCE: float = 1.0
#: Turn angle below which no corner slowdown applies — driving straight or
#: gently curving doesn't need a velocity penalty.
_CORNER_SLOWDOWN_TURN_MIN: float = math.radians(40)
#: At and above this turn angle the slowdown reaches its maximum strength.
_CORNER_SLOWDOWN_TURN_FULL: float = math.radians(90)
#: Absolute target speed (m/s) at the peak of a sharp pass-through corner.
#: This is the SINGLE knob to tune for "how fast through corners" — it's an
#: absolute value, not a fraction of ``wp.speed``, so changing
#: ``NavConfig.default_speed`` later doesn't disturb cornering. The
#: ``_corner_speed_cap`` ramps from ``wp.speed`` at the slowdown-zone
#: boundary down to this target at the corner peak.
_CORNER_TARGET_SPEED: float = 0.3
#: Absolute floor on commanded speed — same gait-min logic as elsewhere,
#: keeps the legs walking even if other multipliers push lower.
_CORNER_MIN_SPEED: float = 0.25
#: Speed cap during BLOCKED recovery — driving backward at full cruise is
#: aggressive when *something* unexpected just happened. Cap to a safer
#: slow walk; ``_CORNER_MIN_SPEED`` still floors it above the gait minimum.
_RECOVERY_SPEED_CAP: float = 0.3
#: Linear-ramp distance after a stationary start (segment 0, or a continue
#: from a must_stop where the dog has just finished the in-place align).
#: Speed rises linearly from the gait floor at dist=0 to full ``wp.speed``
#: at dist=this. Without this the dog snaps from 0 → cruising speed which
#: is jarring at high ``default_speed`` values; symmetric to the terminal
#: brake-ramp on the approach side.
_WARMUP_DISTANCE: float = 0.5
#: Within this distance of a sharp pass-through corner the lookahead is
#: pinned to the waypoint itself instead of extending into the next segment.
#: Set to 0 to disable: with the current slowdown + stall safeguards the
#: adaptive lookahead alone steers cleanly through corners, and any non-zero
#: focus zone delays the dog's curving until *after* it has entered the
#: deviation circle (carrot stays on the corner point right up to the
#: r-trigger boundary). Bump above 0 only if the dog starts "skipping"
#: corners again.
_CORNER_FOCUS_DISTANCE: float = 0.0


@dataclass(slots=True)
class _Segment:
    """One leg of the polyline: from ``start`` to ``end.pose``."""
    start: Pose2D
    end: PathWaypoint


def _project_on_segment(p: Pose2D, a: Pose2D, b: Pose2D) -> tuple[float, float, float]:
    """Project ``p`` onto segment ``a→b``. Returns ``(t, px, py)`` where ``t``
    is the unclamped parameter (so ``t > 1`` means past ``b``)."""
    abx, aby = b.x - a.x, b.y - a.y
    len_sq = abx * abx + aby * aby
    if len_sq < 1e-12:
        return 0.0, a.x, a.y
    t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / len_sq
    t_c = max(0.0, min(1.0, t))
    return t, a.x + t_c * abx, a.y + t_c * aby


class PathExecutor:
    """Straight-line path executor with turn-walk-align phases.

    For each waypoint:
    1. TURNING — rotate in place until facing the waypoint
    2. WALKING — drive forward with small strafing corrections
    3. ALIGNING — at the target, rotate in place to match target heading
    """

    ANGULAR_KP = 1.5
    MAX_ANGULAR_VELOCITY = 0.8
    STATUS_INTERVAL = 0.5
    BLOCKED_TIMEOUT = 5.0
    BLOCKED_DISTANCE_THRESHOLD = 0.05
    BLOCKED_ANGLE_THRESHOLD = math.radians(5)
    ORIENTATION_KP = 1.2
    HEADING_THRESHOLD = math.radians(15)

    def __init__(self) -> None:
        self._path: PlannedPath | None = None
        self._segment_index: int = 0
        self._start_pose: Pose2D | None = None  # snapshot of pose at set_path's first tick
        self._state: NavigationState = NavigationState.IDLE
        self._last_reported_state: NavigationState | None = None
        self._last_status_time: float = 0.0

        self._last_progress_pose: Pose2D | None = None
        self._last_progress_time: float = 0.0

        # True once the dog is within the must_stop waypoint's deviation and
        # the controller has switched to in-place rotation.
        self._aligning: bool = False

        # False between set_path and the first time the dog's heading is
        # within _INITIAL_TURN_THRESHOLD of the lookahead. While False the
        # executor rotates in place instead of driving.
        self._initial_turn_done: bool = False

        # Most recent Pure-Pursuit carrot — surfaced on NavigationStatus for
        # the visualizer. Cleared whenever we're not actively steering.
        self._last_lookahead: Pose2D | None = None

        # Consecutive Pure-Pursuit ticks the dog has spent at a heading
        # error large enough to trigger stall-prevention. If this grows past
        # ``_STALL_TICK_LIMIT`` on a pass-through segment we force-advance
        # the segment so the controller breaks out of any chase-the-bearing
        # loop (real-world rotation can lag the commanded wz and a moving
        # lookahead, producing 360° spins).
        self._stall_tick_counter: int = 0

        # Monotonic timestamp of the last must_stop ARRIVED_SEGMENT
        # transition. ``continue_to_next()`` refuses to advance until
        # ``_MUST_STOP_DWELL_SEC`` has passed, giving a visible pause at
        # corners promoted to must_stop.
        self._must_stop_arrived_at: float | None = None

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def state(self) -> NavigationState:
        return self._state

    @property
    def request_id(self) -> str | None:
        return self._path.request_id if self._path else None

    @property
    def current_target_pose(self) -> Pose2D | None:
        """Pose of the waypoint the executor is currently driving toward.

        ``None`` when no path is loaded or all waypoints consumed. Used by
        ``nav_manager`` for BLOCKED-edge logging.
        """
        if self._path is None:
            return None
        if self._segment_index >= len(self._path.waypoints):
            return None
        return self._path.waypoints[self._segment_index].pose

    def set_path(self, path: PlannedPath) -> None:
        self._path = path
        self._segment_index = 0
        self._state = NavigationState.FOLLOWING
        self._start_pose = None  # snapshot on next update
        self._aligning = False
        self._initial_turn_done = False
        self._last_lookahead = None
        self._stall_tick_counter = 0
        self._last_progress_pose = None
        self._last_progress_time = time.monotonic()
        logger.info(
            f"Following new path (request={path.request_id}, "
            f"{len(path.waypoints)} waypoints)"
        )

    def continue_to_next(self) -> bool:
        """Advance past an ARRIVED_SEGMENT to the next segment.

        Returns True if there is more path to follow, False if we're at the end.
        """
        if self._state != NavigationState.ARRIVED_SEGMENT or self._path is None:
            return False
        # Visible-pause dwell at promoted must_stop corners: refuse to
        # advance until the dog has lingered long enough that an operator
        # can see the stop. NavManager retries every tick.
        arrived_at = self._must_stop_arrived_at
        was_must_stop = arrived_at is not None
        if arrived_at is not None:
            elapsed = time.monotonic() - arrived_at
            if elapsed < _MUST_STOP_DWELL_SEC:
                return False
            self._must_stop_arrived_at = None
        self._segment_index += 1
        self._aligning = False
        self._stall_tick_counter = 0
        self._last_progress_pose = None
        self._last_progress_time = time.monotonic()
        # After a must_stop boundary the dog may face away from the next
        # segment direction: promoted corners come with vacuous
        # ``allowed_orientation_deviation = π`` (no theta requirement),
        # so align_step trivially passes regardless of heading. Re-arm the
        # initial-turn so the dog rotates in place into the new direction
        # before driving — otherwise it loops out wide trying to steer onto
        # the new heading while translating. Pass-through arrivals don't
        # trigger this; the dog is already moving in roughly the right
        # direction so the initial-turn check would no-op anyway.
        if was_must_stop:
            self._initial_turn_done = False
        if self._segment_index >= len(self._path.waypoints):
            self._state = NavigationState.ARRIVED_FINAL
            return False
        self._state = NavigationState.FOLLOWING
        logger.info(
            f"Continuing to waypoint {self._segment_index}/"
            f"{len(self._path.waypoints) - 1}"
        )
        return True

    def reset(self) -> None:
        self._path = None
        self._segment_index = 0
        self._start_pose = None
        self._state = NavigationState.IDLE
        self._aligning = False
        self._initial_turn_done = False
        self._last_lookahead = None
        self._stall_tick_counter = 0
        self._must_stop_arrived_at = None

    def update(
        self, current_pose: Pose2D
    ) -> tuple[MovementCommand, NavigationStatus | None]:
        """Compute the next velocity command + optional status update."""
        if self._path is None or self._state not in (
            NavigationState.FOLLOWING,
            NavigationState.ARRIVED_SEGMENT,
            NavigationState.BLOCKED,
        ):
            return self._stop_cmd(), self._maybe_status(current_pose)

        # ARRIVED_SEGMENT lingers until nav_manager calls continue_to_next.
        # Between calls just hold position.
        if self._state == NavigationState.ARRIVED_SEGMENT:
            return self._stop_cmd(), self._maybe_status(current_pose)

        # BLOCKED: drive back to the last successfully reached waypoint
        # instead of sitting silent. Without this the order is dead in the
        # water — no commands go out, the dog freezes, the operator has no
        # signal of intent.
        if self._state == NavigationState.BLOCKED:
            return self._recover_step(current_pose)

        # Snapshot the start pose on the very first FOLLOWING tick so segment 0
        # has an anchor. Done lazily (vs. set_path) so the snapshot is the
        # actual robot pose, not whatever the nav_manager had cached.
        if self._start_pose is None:
            self._start_pose = current_pose

        current_seg = self._segment(self._segment_index)
        wp = current_seg.end

        # Initial turn-in-place: at the start of a fresh path, if the dog's
        # heading is far off from the first lookahead direction, rotate
        # before translating. Avoids the sideways-slide that Pure-Pursuit's
        # cos-scaled vx would otherwise produce at large initial errors.
        if not self._initial_turn_done:
            turn_cmd = self._maybe_initial_turn(current_pose, current_seg)
            if turn_cmd is not None:
                return turn_cmd, self._maybe_status(current_pose)

        # Aligning at a must_stop waypoint: rotate in place, no translation.
        if self._aligning:
            return self._align_step(current_pose, wp)

        # Have we physically reached the current must_stop waypoint?
        # Use a fraction of allowed_deviation so the dog drives toward the
        # *centre* of the deviation circle instead of stopping at the edge
        # it first entered. VDA5050 calls the node reached at any distance
        # ≤ allowed_deviation, so converging tighter is always fine.
        dist_to_wp = current_pose.distance_to(wp.pose)
        align_trigger_dist = wp.allowed_deviation * _ALIGN_TRIGGER_FACTOR
        if wp.must_stop and dist_to_wp <= align_trigger_dist:
            self._aligning = True
            self._last_lookahead = None
            return self._align_step(current_pose, wp)

        # Terminal approach: inside _TERMINAL_APPROACH_DISTANCE of a must_stop
        # Pure-Pursuit is the wrong tool — switch to direct turn-then-drive so
        # the dog reliably crosses allowed_deviation instead of wobbling.
        if wp.must_stop and dist_to_wp <= _TERMINAL_APPROACH_DISTANCE:
            return self._terminal_step(current_pose, wp)

        # Pass-through: advance the segment as soon as the dog either
        #   (a) crosses the segment-end line geometrically (``t >= 1.0``),
        #       even if laterally far from the waypoint — the main exit
        #       condition, applies to every pass-through corner, OR
        #   (b) enters the "reached" circle (``dist <= allowed_deviation``)
        #       AND the upcoming turn is sharp enough to benefit from arc-
        #       smoothing. Near-straight corners stay precise (only path
        #       (a)) because cutting the last r metres there buys nothing
        #       but mis-aligned VDA5050 lastNodeId tracking.
        t, _, _ = _project_on_segment(current_pose, current_seg.start, wp.pose)
        if not wp.must_stop and (
            t >= 1.0
            or (
                dist_to_wp <= wp.allowed_deviation
                and self._upcoming_turn_is_sharp(current_seg)
            )
        ):
            return self._handle_segment_passed(current_pose)

        # Blocked detection (same heuristic as before: pose stagnation).
        if self._check_blocked(current_pose):
            self._state = NavigationState.BLOCKED
            self._last_lookahead = None
            logger.warning(
                "Robot appears blocked — no progress for "
                f"{self._config.blocked_timeout_sec}s"
            )
            return self._stop_cmd(), self._build_status(current_pose)

        # Pure-Pursuit core: pick a lookahead point on the polyline and steer.
        lookahead = self._compute_lookahead(current_pose, current_seg, t)
        self._last_lookahead = lookahead

        # Stall-loop break-out: if the dog has been sitting at a near-90°
        # heading error for too long (commanded rotation isn't keeping up
        # with a moving bearing — happens when real-world wz lags behind
        # the controller's target), give up trying to corner this segment
        # and force the pass-through advance. The next segment will give
        # the dog a fresh, sensibly-placed lookahead to work with.
        bearing = current_pose.bearing_to(lookahead)
        heading_error = normalize_angle(bearing - current_pose.theta)
        if abs(heading_error) > _STALL_PREVENTION_ANGLE:
            self._stall_tick_counter += 1
            if (
                self._stall_tick_counter > _STALL_TICK_LIMIT
                and not wp.must_stop
                and self._segment_index < len(self._path.waypoints) - 1
            ):
                self._stall_tick_counter = 0
                logger.warning(
                    "Stall break-out at segment {}: force-advancing "
                    "pass-through after {} ticks of large heading error.",
                    self._segment_index, _STALL_TICK_LIMIT,
                )
                return self._handle_segment_passed(current_pose)
        else:
            self._stall_tick_counter = 0

        target_speed = self._target_speed(current_pose, wp, dist_to_wp)
        # Corner caps — pre AND post, both ramp toward _CORNER_TARGET_SPEED:
        #   pre:  approaching a sharp corner ahead → decelerate INTO it
        #   post: just left a sharp corner → keep speed down until the new
        #         heading settles, otherwise outward-overshoot in the old
        #         segment's direction
        # Take the more restrictive of the two when both apply (short
        # segment between two sharp corners).
        pre_cap = self._corner_speed_cap(current_seg, dist_to_wp, target_speed)
        post_cap = self._post_corner_speed_cap(
            current_seg, current_pose, target_speed
        )
        corner_capped = min(pre_cap, post_cap)
        # Warm-up after a stationary start (segment 0 / continue from
        # must_stop) — ramps from rest to the (already corner-capped) speed
        # over the first ``_WARMUP_DISTANCE`` so the dog doesn't snap from
        # zero to cruise.
        warmup = self._warmup_factor(current_pose)
        target_speed = min(
            target_speed, max(_CORNER_MIN_SPEED, corner_capped * warmup)
        )
        return (
            self._steer_toward(current_pose, lookahead, target_speed),
            self._maybe_status(current_pose),
        )

    # ── Segment access ─────────────────────────────────────────────────────

    def _segment(self, index: int) -> _Segment:
        """Build the requested segment on demand. Cheap (3 attr reads)."""
        assert self._path is not None
        waypoints = self._path.waypoints
        if index == 0:
            assert self._start_pose is not None
            start = self._start_pose
        else:
            start = waypoints[index - 1].pose
        return _Segment(start=start, end=waypoints[index])

    # ── Segment-passed handling (pass-through corners) ────────────────────

    def _handle_segment_passed(
        self, pose: Pose2D
    ) -> tuple[MovementCommand, NavigationStatus | None]:
        """Pass-through boundary crossed. Emit ARRIVED_SEGMENT (so the bridge
        marks the VDA5050 node traversed) but keep the velocity smooth by
        steering toward the *next* segment's lookahead.

        nav_manager will call ``continue_to_next()`` on the next tick, flipping
        the state back to FOLLOWING.
        """
        assert self._path is not None
        is_last = self._segment_index >= len(self._path.waypoints) - 1
        if is_last:
            # Nothing past the final waypoint — stop here even if it was
            # technically pass-through (the planner shouldn't emit a
            # pass-through final, but be defensive).
            self._state = NavigationState.ARRIVED_FINAL
            return self._stop_cmd(), self._build_status(pose)

        next_seg = self._segment(self._segment_index + 1)
        # Carrot continuity: use the same projection-based + adaptive-L
        # formula here as ``_compute_lookahead`` will use on the next tick.
        # Computing it naively (L from segment-start, no projection) lands
        # the carrot behind the dog if it overshot the corner, producing a
        # visible backward jump just before the controller advances —
        # exactly what looks like the "lookahead verschwindet" glitch.
        t, _, _ = _project_on_segment(pose, next_seg.start, next_seg.end.pose)
        t_proj = max(0.0, min(1.0, t))
        seg_len = next_seg.start.distance_to(next_seg.end.pose)
        # Anticipate further along if next_seg itself leads into another
        # pass-through corner (the corner one ahead of where we just turned).
        next_next_index = self._segment_index + 2
        factor = 1.0
        if next_next_index < len(self._path.waypoints):
            factor = self._adaptive_factor(
                next_seg, self._segment(next_next_index)
            )
        L = self._config.lookahead_distance * factor
        target_t = min(1.0, t_proj + L / max(seg_len, 1e-9))
        lookahead = self._interpolate(
            next_seg.start, next_seg.end.pose, target_t
        )
        self._last_lookahead = lookahead
        target_speed = next_seg.end.speed
        cmd = self._steer_toward(pose, lookahead, target_speed)

        self._state = NavigationState.ARRIVED_SEGMENT
        logger.info(
            f"Passed segment boundary {self._segment_index} (pass-through)"
        )
        return cmd, self._build_status(pose)

    # ── Initial turn-in-place ──────────────────────────────────────────────

    def _maybe_initial_turn(
        self, pose: Pose2D, current_seg: _Segment
    ) -> MovementCommand | None:
        """One-shot rotate-in-place at path start.

        Returns a rotation command while the dog's heading is more than
        ``_INITIAL_TURN_THRESHOLD`` off from the initial lookahead, or
        ``None`` once it's aligned (also flipping ``_initial_turn_done`` so
        subsequent ticks skip straight to Pure-Pursuit). Publishes the
        lookahead during the turn so the visualizer carrot is visible.

        If the dog is essentially on top of the lookahead (zero-length first
        segment — e.g. the dog set_path'd while parked at the goal) the
        bearing is ill-defined; we skip and defer orientation to the align
        phase downstream.
        """
        t, _, _ = _project_on_segment(
            pose, current_seg.start, current_seg.end.pose
        )
        lookahead = self._compute_lookahead(pose, current_seg, t)
        self._last_lookahead = lookahead
        if pose.distance_to(lookahead) < 0.1:
            self._initial_turn_done = True
            return None
        bearing = pose.bearing_to(lookahead)
        heading_error = normalize_angle(bearing - pose.theta)
        if abs(heading_error) <= _INITIAL_TURN_THRESHOLD:
            self._initial_turn_done = True
            return None
        wz = clamp(
            heading_error * _ANGULAR_KP,
            -self._config.max_angular_velocity,
            self._config.max_angular_velocity,
        )
        return MovementCommand(
            z_deg=math.degrees(wz), source=MovementSource.planner
        )

    # ── Pure-Pursuit lookahead ─────────────────────────────────────────────

    def _compute_lookahead(
        self, pose: Pose2D, current_seg: _Segment, t: float
    ) -> Pose2D:
        """Walk ``lookahead_distance`` along the polyline from the projection
        of ``pose`` onto the current segment.

        No hard corner-cut clamp: the lookahead transitions continuously from
        the current segment into the next so the visual carrot doesn't "pause
        then jump" at a corner. The amount the dog's actual arc deviates from
        the polyline corner is bounded by ``lookahead_distance`` and the
        dog's turning radius — for tighter cornering reduce
        ``NavConfig.lookahead_distance``.

        ``L`` is *anticipated* at sharp pass-through corners: a sharper
        upcoming turn pushes the carrot further onto the next segment, so the
        dog begins arcing into the corner earlier (wider, smoother curve).

        ``must_stop`` still blocks any extension past the current segment so
        the dog reliably hits the brake-and-align zone at the goal.
        """
        assert self._path is not None
        next_index = self._segment_index + 1

        # Near-corner focus: at a sharp pass-through corner, when the dog is
        # within _CORNER_FOCUS_DISTANCE, pin the lookahead to the waypoint
        # itself instead of extending into the next segment. Slowdown alone
        # doesn't redirect the trajectory — the dog still arced wide around
        # the corner and "skipped" the point. Focusing on the waypoint forces
        # the bahn through the actual corner; the r-trigger then advances
        # cleanly once the dog crosses the deviation circle.
        if (
            not current_seg.end.must_stop
            and next_index < len(self._path.waypoints)
        ):
            dist_to_corner = pose.distance_to(current_seg.end.pose)
            if dist_to_corner < _CORNER_FOCUS_DISTANCE:
                next_seg = self._segment(next_index)
                if abs(self._turn_angle(current_seg, next_seg)) >= _R_TRIGGER_TURN_THRESHOLD:
                    return current_seg.end.pose

        L = self._effective_lookahead(current_seg)
        seg_len = current_seg.start.distance_to(current_seg.end.pose)
        # Clamp t into [0,1] for the start point — if we're already past the
        # end (t>1) the pass-through branch in update() will have handled it.
        t_proj = max(0.0, min(1.0, t))
        dist_remaining_on_seg = max(0.0, (1.0 - t_proj)) * seg_len

        can_extend = (
            not current_seg.end.must_stop
            and next_index < len(self._path.waypoints)
        )

        if L <= dist_remaining_on_seg or not can_extend:
            target_t = t_proj + L / max(seg_len, 1e-9)
            target_t = min(1.0, target_t)
            return self._interpolate(
                current_seg.start, current_seg.end.pose, target_t
            )

        # Walk smoothly into the next segment — no analytical corner-cut clamp.
        next_seg = self._segment(next_index)
        next_seg_len = next_seg.start.distance_to(next_seg.end.pose)
        if next_seg_len < 1e-9:
            return current_seg.end.pose
        extension = L - dist_remaining_on_seg
        next_t = min(1.0, extension / next_seg_len)
        return self._interpolate(
            next_seg.start, next_seg.end.pose, next_t
        )

    @staticmethod
    def _interpolate(a: Pose2D, b: Pose2D, t: float) -> Pose2D:
        """Linear interpolation in xy. Theta unused for lookahead targets."""
        return Pose2D(x=a.x + t * (b.x - a.x), y=a.y + t * (b.y - a.y), theta=0.0)

    def _effective_lookahead(self, current_seg: _Segment) -> float:
        """Anticipated lookahead for the current segment.

        Returns the configured ``lookahead_distance`` for must_stop or final
        segments (no anticipation needed), and a scaled-up value when there's
        a sharp pass-through corner ahead. Effect: at a 90°-ish corner the
        carrot lands further onto the next segment, so the dog starts
        turning earlier and traces a wider, smoother arc.
        """
        L = self._config.lookahead_distance
        assert self._path is not None
        next_index = self._segment_index + 1
        if (
            current_seg.end.must_stop
            or next_index >= len(self._path.waypoints)
        ):
            return L
        next_seg = self._segment(next_index)
        return L * self._adaptive_factor(current_seg, next_seg)

    def _adaptive_factor(
        self, seg_a: _Segment, seg_b: _Segment
    ) -> float:
        """Multiplier on ``lookahead_distance`` for the turn between two
        consecutive pass-through segments.

        Ramps linearly from 1× at ``_ANTICIPATE_ANGLE_MIN`` (essentially
        straight) up to ``_ANTICIPATE_MAX_FACTOR`` at ``_ANTICIPATE_ANGLE_FULL``
        and above. Returns 1× whenever no anticipation applies (must_stop
        corner or angle below the floor).
        """
        if seg_a.end.must_stop:
            return 1.0
        turn = abs(self._turn_angle(seg_a, seg_b))
        if turn < _ANTICIPATE_ANGLE_MIN:
            return 1.0
        span = max(_ANTICIPATE_ANGLE_FULL - _ANTICIPATE_ANGLE_MIN, 1e-9)
        progress = min(1.0, (turn - _ANTICIPATE_ANGLE_MIN) / span)
        return 1.0 + progress * (_ANTICIPATE_MAX_FACTOR - 1.0)

    def _corner_speed_cap(
        self,
        current_seg: _Segment,
        dist_to_wp: float,
        base_speed: float,
    ) -> float:
        """Absolute speed cap when approaching a sharp pass-through corner.

        Returns ``base_speed`` when no cap applies (must_stop, last segment,
        outside slowdown zone, or turn too gentle). Otherwise linearly
        blends from ``base_speed`` at the slowdown-zone boundary toward
        ``_CORNER_TARGET_SPEED`` at the corner peak.

        Crucially the target is an *absolute* m/s value, not a fraction —
        bumping ``NavConfig.default_speed`` doesn't make cornering faster.
        Tune corner behaviour by changing ``_CORNER_TARGET_SPEED`` alone.

        Must_stop corners get their own brake-ramp via ``_terminal_step``;
        this only applies on pass-through.
        """
        if current_seg.end.must_stop:
            return base_speed
        assert self._path is not None
        next_index = self._segment_index + 1
        if next_index >= len(self._path.waypoints):
            return base_speed
        if dist_to_wp >= _CORNER_SLOWDOWN_DISTANCE:
            return base_speed
        next_seg = self._segment(next_index)
        turn = abs(self._turn_angle(current_seg, next_seg))
        if turn < _CORNER_SLOWDOWN_TURN_MIN:
            return base_speed
        span = max(
            _CORNER_SLOWDOWN_TURN_FULL - _CORNER_SLOWDOWN_TURN_MIN, 1e-9
        )
        sharpness = min(1.0, (turn - _CORNER_SLOWDOWN_TURN_MIN) / span)
        proximity = 1.0 - dist_to_wp / _CORNER_SLOWDOWN_DISTANCE
        weight = sharpness * proximity  # 0 at boundary, 1 at peak
        blended = base_speed * (1.0 - weight) + _CORNER_TARGET_SPEED * weight
        # Never speed UP — if a slow order already drives below the target,
        # the cap shouldn't override that.
        return min(base_speed, blended)

    def _post_corner_speed_cap(
        self,
        current_seg: _Segment,
        pose: Pose2D,
        base_speed: float,
    ) -> float:
        """Mirror of ``_corner_speed_cap`` on the OTHER side of a sharp
        pass-through corner.

        After advancing past a sharp corner the dog typically has too much
        momentum in the old segment's direction — it accelerates back to
        ``wp.speed`` faster than the steering can pull it onto the new
        line, producing a visible outward overshoot. Capping speed for
        the first ``_CORNER_SLOWDOWN_DISTANCE`` of the new segment lets
        the heading converge onto the new direction before the dog gets
        fast again.

        ``must_stop`` continuations get their own ramp via
        ``_warmup_factor`` — this only applies to pass-through transitions.
        """
        if self._segment_index == 0:
            return base_speed
        assert self._path is not None
        prev_wp = self._path.waypoints[self._segment_index - 1]
        if prev_wp.must_stop:
            return base_speed
        dist_from_start = pose.distance_to(current_seg.start)
        if dist_from_start >= _CORNER_SLOWDOWN_DISTANCE:
            return base_speed
        prev_seg = self._segment(self._segment_index - 1)
        turn = abs(self._turn_angle(prev_seg, current_seg))
        if turn < _CORNER_SLOWDOWN_TURN_MIN:
            return base_speed
        span = max(
            _CORNER_SLOWDOWN_TURN_FULL - _CORNER_SLOWDOWN_TURN_MIN, 1e-9
        )
        sharpness = min(1.0, (turn - _CORNER_SLOWDOWN_TURN_MIN) / span)
        proximity = 1.0 - dist_from_start / _CORNER_SLOWDOWN_DISTANCE
        weight = sharpness * proximity  # 1 right at the corner, 0 at the boundary
        blended = base_speed * (1.0 - weight) + _CORNER_TARGET_SPEED * weight
        return min(base_speed, blended)

    def _warmup_factor(self, pose: Pose2D) -> float:
        """Speed multiplier during the first ``_WARMUP_DISTANCE`` after the
        dog has been stationary — segment 0 of a fresh path, or after a
        must_stop align where the dog physically stopped.

        Returns a linear ramp from 0 at the warm-up anchor to 1.0 at the
        ramp end; the downstream ``_CORNER_MIN_SPEED`` floor on the final
        ``target_speed`` keeps actual ``vx`` above the gait minimum.

        Pass-through continuations skip warm-up — the dog wasn't stopped
        at those, no acceleration jump to smooth.
        """
        assert self._path is not None
        if self._segment_index == 0:
            if self._start_pose is None:
                return 1.0
            anchor = self._start_pose
        else:
            prev = self._path.waypoints[self._segment_index - 1]
            if not prev.must_stop:
                return 1.0
            anchor = prev.pose
        dist = pose.distance_to(anchor)
        if dist >= _WARMUP_DISTANCE:
            return 1.0
        return dist / _WARMUP_DISTANCE

    @staticmethod
    def _turn_angle(seg_a: _Segment, seg_b: _Segment) -> float:
        """Signed turn angle between two consecutive polyline segments."""
        a_dir = math.atan2(
            seg_a.end.pose.y - seg_a.start.y,
            seg_a.end.pose.x - seg_a.start.x,
        )
        b_dir = math.atan2(
            seg_b.end.pose.y - seg_b.start.y,
            seg_b.end.pose.x - seg_b.start.x,
        )
        return normalize_angle(b_dir - a_dir)

    def _upcoming_turn_is_sharp(self, current_seg: _Segment) -> bool:
        """Is the corner at ``current_seg.end`` sharp enough to justify the
        r-trigger early advance?

        Near-straight pass-throughs (< ``_R_TRIGGER_TURN_THRESHOLD``) keep
        projection-only advance so the dog traverses each waypoint precisely
        — VDA5050's lastNodeId reporting expects close passes, and there's
        no smoothness payoff at small angles anyway.
        """
        assert self._path is not None
        next_index = self._segment_index + 1
        if next_index >= len(self._path.waypoints):
            return False
        next_seg = self._segment(next_index)
        return abs(self._turn_angle(current_seg, next_seg)) >= _R_TRIGGER_TURN_THRESHOLD

    # ── Steering / speed ───────────────────────────────────────────────────

    def _steer_toward(
        self, pose: Pose2D, target: Pose2D, target_speed: float
    ) -> MovementCommand:
        bearing = pose.bearing_to(target)
        heading_error = normalize_angle(bearing - pose.theta)
        wz = clamp(
            heading_error * _ANGULAR_KP,
            -self._config.max_angular_velocity,
            self._config.max_angular_velocity,
        )
        # Forward speed: full when aligned, drops with cos(error) and stops
        # contributing past ±90°. Pure-Pursuit naturally re-aims via the
        # angular command in that case.
        align_factor = max(0.0, math.cos(heading_error))
        vx = target_speed * align_factor
        # Stall prevention: at large heading errors the cos-clamp would
        # leave vx = 0 (rotate in place). Real-world rotation is slow, so
        # the pose stops updating; both the projection-advance (t≥1) and
        # the r-trigger then never fire and the controller deadlocks mid-
        # pass-through corner. Floor vx at a walkable speed so the dog
        # always inches forward enough to escape that fixed point.
        if abs(heading_error) > _STALL_PREVENTION_ANGLE:
            vx = max(_STALL_PREVENTION_FLOOR, vx)
        return MovementCommand(
            x=vx, z_deg=math.degrees(wz), source=MovementSource.planner
        )

    def _target_speed(
        self, pose: Pose2D, wp: PathWaypoint, dist_to_wp: float
    ) -> float:
        """Commanded speed for Pure-Pursuit on this waypoint.

        Currently just returns ``wp.speed`` directly — brake-ramping for
        ``must_stop`` happens inside ``_terminal_step`` (which pre-empts
        Pure-Pursuit at ``_TERMINAL_APPROACH_DISTANCE``), not here. Kept
        as a function so the call-site stays readable and there's an
        obvious place to add per-waypoint speed logic later (e.g. honour
        VDA5050 edge ``maxSpeed`` if/when the bridge plumbs it through).
        """
        return wp.speed

    # ── Terminal approach ──────────────────────────────────────────────────

    def _terminal_step(
        self, pose: Pose2D, wp: PathWaypoint
    ) -> tuple[MovementCommand, NavigationStatus | None]:
        """Direct point-to-point controller for the final approach.

        Pure-Pursuit's lookahead breaks down close to a must_stop target:
        the bearing becomes hypersensitive to sub-cm pose changes. This step
        replaces it with a *spiral-in* controller that always aims at the
        waypoint itself — rotate toward it (``wz``) and translate
        proportional to alignment (``vx ∝ cos(error)``).

        Approach-braked: within ``_TERMINAL_BRAKE_DISTANCE`` the speed ramps
        linearly from ``wp.speed`` down to ``_TERMINAL_BRAKE_FLOOR_SPEED``.
        Without the brake the Go2 hits the align step at full cruise and the
        gait drifts the body well past the target during in-place rotation;
        floor stays above the gait minimum so the legs keep walking.

        Signed cos means ``vx`` goes negative when the target sits behind
        the dog, so the Go2 walks backward to recover from an overshoot
        instead of waiting on a slow 180° pivot. Both axes are non-zero
        simultaneously — the dog spirals into ``allowed_deviation`` rather
        than rotating-then-driving — and the align phase one layer up
        handles the final orientation.
        """
        self._last_lookahead = None
        bearing = pose.bearing_to(wp.pose)
        heading_error = normalize_angle(bearing - pose.theta)
        wz = clamp(
            heading_error * _ANGULAR_KP,
            -self._config.max_angular_velocity,
            self._config.max_angular_velocity,
        )
        dist = pose.distance_to(wp.pose)
        speed = wp.speed
        if dist < _TERMINAL_BRAKE_DISTANCE:
            ramped = wp.speed * dist / _TERMINAL_BRAKE_DISTANCE
            speed = min(wp.speed, max(_TERMINAL_BRAKE_FLOOR_SPEED, ramped))
        vx = speed * math.cos(heading_error)
        return (
            MovementCommand(
                x=vx, z_deg=math.degrees(wz), source=MovementSource.planner
            ),
            self._maybe_status(pose),
        )

    # ── Align phase ────────────────────────────────────────────────────────

    def _align_step(
        self, pose: Pose2D, wp: PathWaypoint
    ) -> tuple[MovementCommand, NavigationStatus | None]:
        """Rotate in place toward ``wp``'s heading. Transitions to
        ARRIVED_SEGMENT / ARRIVED_FINAL when within tolerance."""
        assert self._path is not None
        orientation_error = normalize_angle(wp.pose.theta - pose.theta)
        if abs(orientation_error) <= wp.allowed_orientation_deviation:
            self._aligning = False
            is_last = self._segment_index >= len(self._path.waypoints) - 1
            self._state = (
                NavigationState.ARRIVED_FINAL if is_last
                else NavigationState.ARRIVED_SEGMENT
            )
            if not is_last:
                # Intermediate must_stop — start the visible-pause dwell.
                # See ``continue_to_next`` for the gate.
                self._must_stop_arrived_at = time.monotonic()
            logger.info(
                "Arrived at final waypoint" if is_last
                else f"Arrived at segment boundary {self._segment_index}"
            )
            return self._stop_cmd(), self._build_status(pose)
        wz = clamp(
            orientation_error * _ORIENTATION_KP,
            -self._config.max_angular_velocity,
            self._config.max_angular_velocity,
        )
        return (
            MovementCommand(z_deg=math.degrees(wz), source=MovementSource.planner),
            self._maybe_status(pose),
        )

    # ── Blocked recovery ───────────────────────────────────────────────────

    def _recover_step(
        self, pose: Pose2D
    ) -> tuple[MovementCommand, NavigationStatus | None]:
        """After a BLOCKED, drive back toward the last successfully reached
        waypoint (start of the current segment).

        Without this the dog freezes — no velocity commands go out and the
        order is dead. Driving back to a known-safe point gives the operator
        a clear visual signal and parks the dog somewhere reachable from the
        rest of the map.

        Uses the same spiral-in geometry as ``_terminal_step``: heading-aware
        ``cos(error)`` so the dog walks backward when the target sits behind
        it instead of waiting on a slow in-place pivot. State stays BLOCKED
        throughout — recovery doesn't pretend the order succeeded.
        """
        if self._path is None:
            return self._stop_cmd(), self._maybe_status(pose)

        # Last good position = start of the current segment. For segment 0
        # that's the start_pose snapshot (where the dog was when set_path
        # ran); for later segments it's the previous waypoint, which IS the
        # last VDA5050 node the dog cleared.
        if self._segment_index == 0:
            target = self._start_pose if self._start_pose is not None else pose
        else:
            target = self._path.waypoints[self._segment_index - 1].pose

        # Already at the recovery target — hold position. Carrot cleared
        # because there's nothing left to steer toward.
        if pose.distance_to(target) < 0.15:
            self._last_lookahead = None
            return self._stop_cmd(), self._maybe_status(pose)

        self._last_lookahead = target
        bearing = pose.bearing_to(target)
        heading_error = normalize_angle(bearing - pose.theta)
        wz = clamp(
            heading_error * _ANGULAR_KP,
            -self._config.max_angular_velocity,
            self._config.max_angular_velocity,
        )
        # Recovery speed: cap at ``_RECOVERY_SPEED_CAP`` so the dog doesn't
        # zoom backward at full cruise — BLOCKED means *something* unexpected
        # happened, slower retreat is safer. Floor at the gait minimum so
        # the legs still walk.
        speed = max(
            _CORNER_MIN_SPEED,
            min(self._path.waypoints[self._segment_index].speed, _RECOVERY_SPEED_CAP),
        )
        vx = speed * math.cos(heading_error)
        return (
            MovementCommand(
                x=vx, z_deg=math.degrees(wz), source=MovementSource.planner
            ),
            self._maybe_status(pose),
        )

    # ── Blocked detection ──────────────────────────────────────────────────

    def _check_blocked(self, pose: Pose2D) -> bool:
        now = time.monotonic()
        # Convergence zone: within _CONVERGENCE_ZONE of a must_stop the dog
        # may be doing slow corrections (re-aligning after a corner overshoot,
        # heading-rotation that the gait engine renders very slowly). The
        # pose-stagnation heuristic was tuned for normal-speed driving and
        # mistakes those corrections for being stuck. Suppress BLOCKED here
        # and reset the progress baseline so the timer doesn't carry over.
        if self._path is not None and self._segment_index < len(self._path.waypoints):
            wp = self._path.waypoints[self._segment_index]
            if wp.must_stop and pose.distance_to(wp.pose) < _CONVERGENCE_ZONE:
                self._last_progress_pose = pose
                self._last_progress_time = now
                return False

        if self._last_progress_pose is None:
            self._last_progress_pose = pose
            self._last_progress_time = now
            return False
        moved = pose.distance_to(self._last_progress_pose)
        rotated = abs(normalize_angle(pose.theta - self._last_progress_pose.theta))
        if moved > _BLOCKED_DISTANCE_THRESHOLD or rotated > _BLOCKED_ANGLE_THRESHOLD:
            self._last_progress_pose = pose
            self._last_progress_time = now
            return False
        return (now - self._last_progress_time) >= self._config.blocked_timeout_sec

    # ── Status emission ────────────────────────────────────────────────────

    @staticmethod
    def _stop_cmd() -> MovementCommand:
        return MovementCommand(source=MovementSource.planner)

    def _maybe_status(self, pose: Pose2D) -> NavigationStatus | None:
        now = time.monotonic()
        if self._state != self._last_reported_state:
            return self._build_status(pose)
        if (
            self._state == NavigationState.FOLLOWING
            and (now - self._last_status_time) >= _STATUS_INTERVAL_SEC
        ):
            return self._build_status(pose)
        return None

    def _build_status(self, pose: Pose2D) -> NavigationStatus:
        self._last_reported_state = self._state
        self._last_status_time = time.monotonic()
        distance_to_target = None
        distance_to_final = None
        segment_index = None
        if self._path and self._segment_index < len(self._path.waypoints):
            current_wp = self._path.waypoints[self._segment_index]
            distance_to_target = pose.distance_to(current_wp.pose)
            final_wp = self._path.waypoints[-1]
            distance_to_final = pose.distance_to(final_wp.pose)
            # current_segment_index counts how many is_segment_boundary
            # waypoints we've already cleared — matches the bridge's mapping
            # from nav events back to VDA5050 node ids.
            segment_index = sum(
                1
                for wp in self._path.waypoints[: self._segment_index]
                if wp.is_segment_boundary
            )
        return NavigationStatus(
            state=self._state,
            current_pose=pose,
            distance_to_target=distance_to_target,
            distance_to_final=distance_to_final,
            current_segment_index=segment_index,
            request_id=self._path.request_id if self._path else None,
            lookahead_point=self._last_lookahead,
        )
