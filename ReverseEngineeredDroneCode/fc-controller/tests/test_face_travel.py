"""
Face Direction of Travel.

Frames follow the Novex VIO: OpenCV camera convention (X right, Y down, Z forward),
so with a level forward-facing camera "up" is -Y. Headings are counter-clockwise
seen from above (positive = turned left).

The closed-loop tests use a small kinematic TEST FIXTURE (ClosedLoopFixture) to check
convergence, smoothness and that course lock stops the drone from circling. It exists
only in this file. Its yaw rate per unit stick is an ASSUMPTION: the real drone's value
is UNKNOWN, which is exactly why the controller closes the loop on measured heading.
"""

import math
import os
import tempfile
import unittest

from controller.face_travel import (
    FaceTravel,
    FaceTravelConfig,
    HorizontalFrame,
    Mode,
    MotionSample,
    quat_rotate,
    wrap,
)
from controller.flight import FlightController
from controller.protocol import DEVICE_TYPE_TC

UP = (0.0, -1.0, 0.0)          # level camera: up is -Y


def quat_for_heading(psi: float):
    """Rotation of the camera by psi counter-clockwise about 'up' (-Y)."""
    return (0.0, -math.sin(psi / 2.0), 0.0, math.cos(psi / 2.0))


def world_velocity(speed: float, direction: float):
    """Horizontal velocity at `direction` (CCW from +Z); left is -X."""
    return (-speed * math.sin(direction), 0.0, speed * math.cos(direction))


class Clock:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


class Source:
    """Returns whatever sample the test sets."""

    def __init__(self):
        self.sample = None

    def __call__(self):
        return self.sample


def make(**cfg):
    clock, source = Clock(), Source()
    ft = FaceTravel(source, FaceTravelConfig(**cfg), clock)
    ft.set_enabled(True)
    return ft, clock, source


def sample(clock, heading=0.0, speed=0.0, direction=0.0, **kw):
    return MotionSample(received=clock.t, velocity=world_velocity(speed, direction),
                        orientation=quat_for_heading(heading), up=kw.pop("up", UP), **kw)


NEUTRAL = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0, "throttle": 0.0}


def run(ft, clock, source, inputs=NEUTRAL, ticks=1, **sample_kw):
    out = None
    for _ in range(ticks):
        clock.t += 0.05
        source.sample = sample(clock, **sample_kw)
        out = ft.apply(dict(inputs), clock.t)
    return out


class TestGeometry(unittest.TestCase):
    def test_quaternion_heading_convention(self):
        nose = quat_rotate(quat_for_heading(math.pi / 2), (0.0, 0.0, 1.0))
        self.assertAlmostEqual(nose[0], -1.0, places=6)      # turned left -> nose to -X
        frame = HorizontalFrame(UP)
        self.assertAlmostEqual(frame.angle(nose), math.pi / 2, places=6)

    def test_right_is_clockwise(self):
        frame = HorizontalFrame(UP)
        self.assertAlmostEqual(frame.angle((1.0, 0.0, 0.0)), -math.pi / 2, places=6)

    def test_wrap(self):
        self.assertAlmostEqual(wrap(3 * math.pi / 2), -math.pi / 2)
        self.assertAlmostEqual(wrap(-3 * math.pi / 2), math.pi / 2)
        self.assertAlmostEqual(wrap(math.pi), math.pi)

    def test_tilted_camera_still_gives_horizontal_heading(self):
        # Drone pitched nose-down 20 deg while flying forward: the heading must not change.
        tilt = math.radians(20)
        q = (math.sin(tilt / 2), 0.0, 0.0, math.cos(tilt / 2))   # about camera X
        nose = quat_rotate(q, (0.0, 0.0, 1.0))
        frame = HorizontalFrame(UP)
        self.assertAlmostEqual(frame.angle((nose[0], 0.0, nose[2])), 0.0, places=6)


class TestDisabled(unittest.TestCase):
    def test_disabled_returns_inputs_untouched(self):
        ft = FaceTravel(lambda: None)
        inputs = {"roll": 0.3, "pitch": -0.7, "yaw": 0.2, "throttle": 0.5}
        self.assertEqual(ft.apply(dict(inputs)), inputs)

    def test_disabled_packets_are_identical(self):
        calls = []

        def source():
            calls.append(1)
            return None

        ft = FaceTravel(source)          # present but disabled
        plain = FlightController(sender=lambda b: True, device_type=lambda: DEVICE_TYPE_TC)
        with_ft = FlightController(sender=lambda b: True, device_type=lambda: DEVICE_TYPE_TC, face_travel=ft)
        for keys in ([], ["w"], ["d", "w"], ["Left"], ["Right", "Up"], ["s", "a", "Down"]):
            for fc in (plain, with_ft):
                fc.keyboard.release_all()
                for k in keys:
                    fc.keyboard.press(k)
            self.assertEqual(plain.build_current_packet().data, with_ft.build_current_packet().data, keys)
        self.assertEqual(calls, [], "motion source must not even be consulted when disabled")


class TestAutoYaw(unittest.TestCase):
    def test_moving_right_turns_right(self):
        ft, clock, source = make()
        out = run(ft, clock, source, ticks=20, speed=0.5, direction=-math.pi / 2)
        self.assertGreater(out["yaw"], 0.0)                  # yaw byte > 128
        self.assertEqual(ft.status().mode, Mode.TURNING)

    def test_moving_left_turns_left(self):
        ft, clock, source = make()
        out = run(ft, clock, source, ticks=20, speed=0.5, direction=math.pi / 2)
        self.assertLess(out["yaw"], 0.0)

    def test_moving_forward_needs_no_turn(self):
        ft, clock, source = make()
        out = run(ft, clock, source, ticks=20, speed=0.5, direction=0.0)
        self.assertEqual(out["yaw"], 0.0)
        self.assertEqual(ft.status().mode, Mode.ALIGNED)

    def test_diagonal_travel_turns_proportionally(self):
        ft, clock, source = make(max_yaw=1.0, gain=0.5)
        out = run(ft, clock, source, ticks=40, speed=0.5, direction=-math.pi / 4)
        # 45 deg error * gain 0.5/rad = 0.39; well below the cap, so it is proportional
        self.assertAlmostEqual(out["yaw"], 0.5 * math.pi / 4, places=2)

    def test_hovering_holds_yaw(self):
        ft, clock, source = make()
        out = run(ft, clock, source, ticks=20, speed=0.05, direction=-math.pi / 2)
        self.assertEqual(out["yaw"], 0.0)
        self.assertEqual(ft.status().mode, Mode.HOLDING)

    def test_speed_hysteresis(self):
        ft, clock, source = make()
        run(ft, clock, source, ticks=5, speed=0.15, direction=-math.pi / 2)
        self.assertEqual(ft.status().mode, Mode.HOLDING)      # below start speed
        run(ft, clock, source, ticks=5, speed=0.30, direction=-math.pi / 2)
        self.assertEqual(ft.status().mode, Mode.TURNING)
        run(ft, clock, source, ticks=5, speed=0.15, direction=-math.pi / 2)
        self.assertEqual(ft.status().mode, Mode.TURNING)      # still above stop speed
        run(ft, clock, source, ticks=40, speed=0.02, direction=-math.pi / 2)
        self.assertEqual(ft.status().mode, Mode.HOLDING)

    def test_output_is_slew_limited(self):
        ft, clock, source = make(slew_rate=1.5, max_yaw=1.0)
        previous = 0.0
        for _ in range(30):
            out = run(ft, clock, source, speed=1.0, direction=-math.pi / 2)
            self.assertLessEqual(abs(out["yaw"] - previous), 1.5 * 0.05 + 1e-9)
            previous = out["yaw"]

    def test_output_capped(self):
        ft, clock, source = make(max_yaw=0.4)
        out = run(ft, clock, source, ticks=60, speed=1.0, direction=-math.pi / 2)
        self.assertLessEqual(abs(out["yaw"]), 0.4 + 1e-9)

    def test_stop_ramps_down_instead_of_snapping(self):
        ft, clock, source = make()
        out = run(ft, clock, source, ticks=30, speed=0.8, direction=-math.pi / 2)
        self.assertGreater(out["yaw"], 0.3)
        out = run(ft, clock, source, ticks=1, speed=0.0, direction=0.0, heading=0.0)
        self.assertGreater(out["yaw"], 0.0)                   # still decaying, not zeroed

    def test_noisy_velocity_near_alignment_does_not_jitter(self):
        ft, clock, source = make()
        run(ft, clock, source, ticks=20, speed=0.6, direction=0.0)
        signs = set()
        for i in range(100):
            jitter = math.radians(4.0) * (1 if i % 2 else -1)  # +-4 deg noise, inside deadband
            out = run(ft, clock, source, speed=0.6, direction=jitter)
            if out["yaw"]:
                signs.add(out["yaw"] > 0)
        self.assertEqual(signs, set(), "commanded yaw while aligned within noise")

    def test_turning_around_keeps_one_direction(self):
        ft, clock, source = make()
        run(ft, clock, source, ticks=10, speed=0.6, direction=math.radians(170))
        first = ft.status().error_deg
        out = run(ft, clock, source, ticks=5, speed=0.6, direction=math.radians(-175))
        self.assertGreater(first, 0)
        self.assertGreater(ft.status().error_deg, 0, "flipped turn direction across 180")
        self.assertLess(out["yaw"], 0.0)

    def test_throttle_never_modified(self):
        ft, clock, source = make()
        for throttle in (-1.0, -0.3, 0.0, 0.6, 1.0):
            out = run(ft, clock, source, dict(NEUTRAL, throttle=throttle, pitch=1.0), ticks=5,
                      speed=0.8, direction=-math.pi / 2, heading=0.4)
            self.assertEqual(out["throttle"], throttle)


class TestManualOverride(unittest.TestCase):
    def test_manual_yaw_wins_then_resumes_smoothly(self):
        ft, clock, source = make()
        run(ft, clock, source, ticks=20, speed=0.8, direction=-math.pi / 2)
        out = run(ft, clock, source, dict(NEUTRAL, yaw=-0.9), speed=0.8, direction=-math.pi / 2)
        self.assertEqual(out["yaw"], -0.9)
        self.assertEqual(ft.status().mode, Mode.OVERRIDE)
        out = run(ft, clock, source, speed=0.8, direction=-math.pi / 2)
        self.assertLessEqual(abs(out["yaw"]), 1.5 * 0.05 + 1e-9)   # ramps up from zero


class TestSuspension(unittest.TestCase):
    def assert_passthrough(self, ft, clock, source, expected_mode, **sample_kw):
        inputs = {"roll": 0.4, "pitch": 0.6, "yaw": 0.0, "throttle": 0.2}
        clock.t += 0.05
        source.sample = sample(clock, **sample_kw) if sample_kw is not None else None
        self.assertEqual(ft.apply(dict(inputs), clock.t), inputs)
        self.assertEqual(ft.status().mode, expected_mode)

    def test_no_vio(self):
        ft, clock, source = make()
        clock.t += 0.05
        inputs = {"roll": 0.4, "pitch": 0.6, "yaw": 0.0, "throttle": 0.2}
        self.assertEqual(ft.apply(dict(inputs), clock.t), inputs)
        self.assertEqual(ft.status().mode, Mode.WAITING)

    def test_not_tracking(self):
        ft, clock, source = make()
        self.assert_passthrough(ft, clock, source, Mode.SUSPENDED, speed=1.0, tracking=False)

    def test_lost_frames(self):
        ft, clock, source = make()
        self.assert_passthrough(ft, clock, source, Mode.SUSPENDED, speed=1.0, lost_frames=3)

    def test_no_floor(self):
        ft, clock, source = make()
        self.assert_passthrough(ft, clock, source, Mode.SUSPENDED, speed=1.0, up=None)

    def test_stale(self):
        ft, clock, source = make()
        source.sample = sample(clock, speed=1.0, direction=-1.0)
        clock.t += 1.0
        inputs = {"roll": 0.4, "pitch": 0.6, "yaw": 0.0, "throttle": 0.2}
        self.assertEqual(ft.apply(dict(inputs), clock.t), inputs)
        self.assertIn("stale", ft.status().reason)


class TestCourseLock(unittest.TestCase):
    def test_activation_is_bumpless(self):
        ft, clock, source = make()
        inputs = dict(NEUTRAL, pitch=0.8, roll=-0.3)
        out = run(ft, clock, source, inputs, heading=1.1, speed=0.0)
        self.assertAlmostEqual(out["pitch"], 0.8, places=9)
        self.assertAlmostEqual(out["roll"], -0.3, places=9)

    def test_forward_stays_world_forward_after_turning_left(self):
        ft, clock, source = make()
        run(ft, clock, source, heading=0.0)                  # lock reference at 0
        out = run(ft, clock, source, dict(NEUTRAL, pitch=1.0), heading=math.pi / 2)
        # The nose is now 90 deg left of the reference, so reference-forward is body-right.
        self.assertAlmostEqual(out["roll"], 1.0, places=6)
        self.assertAlmostEqual(out["pitch"], 0.0, places=6)

    def test_diagonal_is_kept_on_the_unit_circle(self):
        ft, clock, source = make()
        out = run(ft, clock, source, dict(NEUTRAL, pitch=1.0, roll=1.0), heading=0.0)
        self.assertAlmostEqual(math.hypot(out["pitch"], out["roll"]), 1.0, places=6)
        self.assertAlmostEqual(out["pitch"], out["roll"], places=6)

    def test_reference_recaptured_after_suspension(self):
        ft, clock, source = make()
        run(ft, clock, source, heading=0.0)
        run(ft, clock, source, heading=1.0, tracking=False)  # suspended
        out = run(ft, clock, source, dict(NEUTRAL, pitch=1.0), heading=1.0)
        self.assertAlmostEqual(out["pitch"], 1.0, places=6)  # bumpless again


class ClosedLoopFixture:
    """
    TEST FIXTURE ONLY - a minimal kinematic stand-in for the airframe so the controller
    can be exercised in closed loop. Assumptions (not facts about the real drone):
      * yaw rate = plant_sign * stick * YAW_RATE, clockwise for positive stick
      * horizontal velocity follows the body-frame roll/pitch command with a first-order lag
    """

    YAW_RATE = math.radians(90)   # per unit stick; UNKNOWN for the real drone
    SPEED = 1.0                   # m/s per unit stick
    LAG = 0.3                     # s

    def __init__(self, ft, clock, source, plant_sign=1, heading=0.0):
        self.ft, self.clock, self.source = ft, clock, source
        self.plant_sign = plant_sign
        self.heading = heading
        self.vel = (0.0, 0.0)          # world, (forward-of-origin, left-of-origin)

    def step(self, inputs):
        v = self.vel
        speed = math.hypot(*v)
        direction = math.atan2(v[1], v[0]) if speed > 1e-9 else 0.0
        self.clock.t += 0.05
        self.source.sample = sample(self.clock, heading=self.heading, speed=speed, direction=direction)
        out = self.ft.apply(dict(inputs), self.clock.t)
        # airframe response
        self.heading = wrap(self.heading - self.plant_sign * out["yaw"] * self.YAW_RATE * 0.05)
        f, l = out["pitch"], -out["roll"]
        body = math.atan2(l, f)
        mag = min(1.0, math.hypot(f, l)) * self.SPEED
        target = (mag * math.cos(self.heading + body), mag * math.sin(self.heading + body))
        a = 1 - math.exp(-0.05 / self.LAG)
        self.vel = (v[0] + a * (target[0] - v[0]), v[1] + a * (target[1] - v[1]))
        return out


class TestClosedLoop(unittest.TestCase):
    def test_strafing_right_converges_to_nose_first_without_circling(self):
        ft, clock, source = make()
        sim = ClosedLoopFixture(ft, clock, source)
        directions, yaws = [], []
        for _ in range(300):                                   # 15 s, pilot holds "right"
            out = sim.step(dict(NEUTRAL, roll=1.0))
            directions.append(math.atan2(sim.vel[1], sim.vel[0]))
            yaws.append(out["yaw"])
        # 1) the nose ends up facing the travel direction (right = -90 deg)
        self.assertAlmostEqual(math.degrees(sim.heading), -90, delta=8)
        # 2) course lock: the drone kept travelling right the whole time (never circled)
        for d in directions[20:]:
            self.assertAlmostEqual(math.degrees(d), -90, delta=15)
        # 3) it ends flying nose-first: nearly pure forward pitch in body frame
        self.assertGreater(out["pitch"], 0.95)
        # 4) smooth: the yaw command never reverses sign (no oscillation / jitter)
        nonzero = [y for y in yaws if abs(y) > 1e-6]
        self.assertTrue(all(y > 0 for y in nonzero))

    def test_backward_turns_around(self):
        ft, clock, source = make()
        sim = ClosedLoopFixture(ft, clock, source)
        for _ in range(400):
            sim.step(dict(NEUTRAL, pitch=-1.0))
        self.assertAlmostEqual(abs(math.degrees(sim.heading)), 180, delta=10)

    def test_diagonal_converges(self):
        ft, clock, source = make()
        sim = ClosedLoopFixture(ft, clock, source)
        for _ in range(300):
            sim.step(dict(NEUTRAL, pitch=1.0, roll=-1.0))      # forward-left
        self.assertAlmostEqual(math.degrees(sim.heading), 45, delta=8)

    def test_without_course_lock_body_frame_strafing_would_circle(self):
        """Documents WHY course lock exists: plain body-frame sticks + auto-yaw circle."""
        ft, clock, source = make()
        ft._course_lock = lambda inputs, heading: {"pitch": inputs["pitch"], "roll": inputs["roll"]}
        sim = ClosedLoopFixture(ft, clock, source)
        turned = 0.0
        for _ in range(300):
            before = sim.heading
            sim.step(dict(NEUTRAL, roll=1.0))
            turned += wrap(sim.heading - before)
        # The travel direction rotates with the nose, so the nose chases it round and round.
        self.assertGreater(abs(math.degrees(turned)), 360)

    def test_inverted_yaw_sign_faults_instead_of_spinning(self):
        ft, clock, source = make()
        sim = ClosedLoopFixture(ft, clock, source, plant_sign=-1)   # the airframe turns the other way
        faulted_at = None
        for i in range(200):
            out = sim.step(dict(NEUTRAL, roll=1.0))
            if ft.status().mode == Mode.FAULT:
                faulted_at = i
                break
        self.assertIsNotNone(faulted_at, "never detected the inverted yaw")
        self.assertLess(faulted_at * 0.05, 4.0)
        self.assertIn("yaw sign", ft.status().reason)
        # latched: sticks pass straight through from now on
        inputs = dict(NEUTRAL, roll=0.5)
        self.assertEqual(ft.apply(dict(inputs), clock.t + 0.05), inputs)
        ft.set_enabled(False)
        ft.set_enabled(True)
        self.assertEqual(ft.status().mode, Mode.WAITING)       # cleared by toggling


class TestVioClient(unittest.TestCase):
    """Protocol test against a local socket speaking the daemon's line protocol."""

    def test_polls_state_and_floor_over_unix_socket(self):
        import json
        import socket
        import threading
        import time
        from link.vio_client import VioClient

        path = os.path.join(tempfile.mkdtemp(), "vio.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(path)
        server.listen(1)
        commands = []
        # Field names and layout as in StateServer::formatState / formatFloor.
        state = {"timestamp": 1.0, "position": [0, 0, 0], "velocity": [0.4, 0.0, 0.1],
                 "orientation": [0.0, 0.0, 0.0, 1.0], "tracking": True, "feature_count": 80,
                 "lost_frames": 0}
        floor = {"valid": True, "status": "TRACKING", "confidence": 0.9,
                 "reported_plane": [0.0, -1.0, 0.0, 1.2]}

        def serve():
            conn, _ = server.accept()
            f = conn.makefile("rwb")
            for line in f:
                cmd = line.decode().strip()
                commands.append(cmd)
                reply = state if cmd == "GET_STATE" else floor if cmd == "GET_FLOOR" else {"error": "unknown command"}
                f.write((json.dumps(reply) + "\n").encode())
                f.flush()

        threading.Thread(target=serve, daemon=True).start()
        record = os.path.join(tempfile.mkdtemp(), "vio.log")
        client = VioClient(f"unix:{path}", poll_hz=50, record_path=record)
        client.start()
        try:
            end = time.monotonic() + 3.0
            while client.latest() is None and time.monotonic() < end:
                time.sleep(0.02)
            s = client.latest()
            self.assertIsNotNone(s)
            self.assertEqual(s.velocity, (0.4, 0.0, 0.1))
            self.assertEqual(s.up, (0.0, -1.0, 0.0))
            self.assertTrue(s.tracking)
            self.assertIn("GET_FLOOR", commands)
            self.assertIn("GET_STATE", commands)
        finally:
            client.stop()
            server.close()
        with open(record) as f:
            self.assertIn("GET_STATE", f.read())

    def test_address_parsing(self):
        import socket
        from link.vio_client import parse_address
        self.assertEqual(parse_address("tcp://127.0.0.1:7700"), (socket.AF_INET, ("127.0.0.1", 7700)))
        self.assertEqual(parse_address("unix:/tmp/novex-vio.sock"), (socket.AF_UNIX, "/tmp/novex-vio.sock"))
        with self.assertRaises(ValueError):
            parse_address("http://x")


if __name__ == "__main__":
    unittest.main()
