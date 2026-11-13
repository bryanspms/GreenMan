import math
import random
import tkinter as tk
import unittest
from datetime import date
from unittest.mock import Mock, patch

from face import (
    BIRD_COLORS,
    BLINK_LID_LEVELS,
    FACE_HEIGHT,
    FACE_SCALE,
    FACE_WIDTH,
    GLASSES_COLOR,
    GLASSES_WIDTH,
    NOSE_TWITCH_OFFSETS,
    RECORDING_EYE_COLOR,
    SLEEP_BLINK_COUNT,
    SLEEP_BLINK_SECONDS,
    SLEEP_IDLE_SECONDS,
    SLEEP_YAWN_SECONDS,
    WAITING_EYE_COLOR,
    VISITOR_FLIGHT_SECONDS,
    VISITOR_TAG,
    EyeLegend,
    GreenManFace,
)

COLORS = {
    "background": "#e8f1e8",
    "text": "#183b24",
    "green": "#2f6b3f",
    "green_selected": "#c8dfca",
}


class FlyingVisitorTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(self.root.destroy)
        self.face = GreenManFace(self.root, self.root, COLORS, COLORS["background"])
        self.addCleanup(
            lambda: self.root.after_cancel(self.face._eye_after)
            if self.face._eye_after is not None else None
        )

    def test_visitor_crosses_face_without_changing_states(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        face._visitor_choices = ["bee"]
        with patch("face.time.monotonic", return_value=0.0) as now, patch(
            "face.random.choice", return_value=1
        ), patch("face.random.uniform", return_value=60.0), patch.object(
            face.root, "after", return_value="visitor-timer"
        ) as after:
            face.waiting = face.loading = face.recording = face.speaking = True
            face.sleeping = True
            previous_activity = face._last_activity
            face._start_visitor()
            items = face.canvas.find_withtag(VISITOR_TAG)
            self.assertEqual(len(items), 4)
            initial = face.canvas.coords(items[2])
            tick = after.call_args.args[1]
            now.return_value = VISITOR_FLIGHT_SECONDS / 2
            tick()
            self.assertGreater(face.canvas.coords(items[2])[0], initial[0])
            self.assertEqual(
                (face.waiting, face.loading, face.recording, face.speaking, face.sleeping),
                (True, True, True, True, True),
            )
            self.assertEqual(face._last_activity, previous_activity)
            face._visitor_after = None
            face.canvas.delete(VISITOR_TAG)

    def test_moth_finishes_reverse_flight_and_schedules_next_visit(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        face._visitor_choices = ["moth"]
        with patch("face.time.monotonic", return_value=0.0) as now, patch(
            "face.random.choice", return_value=-1
        ), patch("face.random.uniform", return_value=60.0), patch.object(
            face.root, "after", return_value="visitor-timer"
        ) as after:
            face._start_visitor()
            items = face.canvas.find_withtag(VISITOR_TAG)
            initial = face.canvas.coords(items[2])
            tick = after.call_args.args[1]
            now.return_value = VISITOR_FLIGHT_SECONDS / 2
            tick()
            self.assertLess(face.canvas.coords(items[2])[0], initial[0])
            now.return_value = VISITOR_FLIGHT_SECONDS
            tick()
            self.assertEqual(face.canvas.find_withtag(VISITOR_TAG), ())
            self.assertEqual(after.call_args.args[1], face._start_visitor)
            face._visitor_after = None

    def test_butterfly_is_colorful_and_flaps_across_face(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        face._visitor_choices = ["butterfly"]
        with patch("face.time.monotonic", return_value=0.0) as now, patch(
            "face.random.choice", return_value=1
        ), patch("face.random.uniform", return_value=60.0), patch.object(
            face.root, "after", return_value="visitor-timer"
        ) as after:
            face._start_visitor()
            items = face.canvas.find_withtag(VISITOR_TAG)
            self.assertEqual(len(items), 6)
            self.assertEqual(
                [face.canvas.itemcget(item, "fill") for item in (items[0], items[1], items[4])],
                ["#f080d0", "#69a9f5", "#ffe76b"],
            )
            initial_wing = face.canvas.coords(items[0])
            tick = after.call_args.args[1]
            now.return_value = VISITOR_FLIGHT_SECONDS / 2
            tick()
            moved_wing = face.canvas.coords(items[0])
            self.assertGreater(moved_wing[0], initial_wing[0])
            self.assertNotEqual(
                moved_wing[3] - moved_wing[1], initial_wing[3] - initial_wing[1]
            )
            now.return_value = VISITOR_FLIGHT_SECONDS
            tick()
            self.assertEqual(face.canvas.find_withtag(VISITOR_TAG), ())
            self.assertEqual(after.call_args.args[1], face._start_visitor)
            face._visitor_after = None

    def test_visitors_are_shuffled_in_groups_of_four(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        seeded_random = random.Random(123)
        seen = []
        with patch("face.time.monotonic", return_value=0.0) as now, patch(
            "face.random.shuffle", side_effect=seeded_random.shuffle
        ) as shuffle, patch(
            "face.random.choice", side_effect=lambda choices: choices[-1]
        ), patch(
            "face.random.uniform", return_value=60.0
        ), patch.object(face.root, "after", return_value="visitor-timer") as after:
            for _ in range(8):
                now.return_value = 0.0
                face._start_visitor()
                items = face.canvas.find_withtag(VISITOR_TAG)
                seen.append(face.canvas.itemcget(items[2], "fill"))
                tick = after.call_args.args[1]
                now.return_value = VISITOR_FLIGHT_SECONDS
                tick()
                self.assertEqual(face.canvas.find_withtag(VISITOR_TAG), ())
            self.assertEqual(shuffle.call_count, 2)
            expected = {"#e7b733", "#8a7f6a", "#53315f", BIRD_COLORS[-1]}
            self.assertEqual(set(seen[:4]), expected)
            self.assertEqual(set(seen[4:]), expected)
            face._visitor_after = None

    def test_visit_delay_is_random_between_one_and_five_minutes(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        with patch("face.random.uniform", side_effect=[60_000, 300_000]) as uniform, patch.object(
            face.root, "after", return_value="visitor-timer"
        ) as after:
            for delay in (60_000, 300_000):
                face._schedule_visitor()
                after.assert_called_with(delay, face._start_visitor)
                face._visitor_after = None
            self.assertEqual(uniform.call_count, 2)
            uniform.assert_called_with(60_000, 300_000)

    def test_preview_cancels_wait_and_does_not_interrupt_active_flight(self) -> None:
        face = self.face
        pending = face._visitor_after
        face.show_next_visitor()
        items = face.canvas.find_withtag(VISITOR_TAG)
        active = face._visitor_after
        self.assertTrue(items)
        self.assertNotEqual(active, pending)
        self.assertNotIn(pending, self.root.tk.splitlist(self.root.tk.call("after", "info")))
        face.show_next_visitor()
        self.assertEqual(face.canvas.find_withtag(VISITOR_TAG), items)
        self.assertEqual(face._visitor_after, active)

    def test_preview_respects_disabled_animations(self) -> None:
        face = self.face
        face.set_animations(False)
        choices = face._visitor_choices[:]
        face.show_next_visitor()
        self.assertEqual(face.canvas.find_withtag(VISITOR_TAG), ())
        self.assertIsNone(face._visitor_after)
        self.assertEqual(face._visitor_choices, choices)

    def test_insects_can_loop_in_either_direction(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        with patch("face.time.monotonic", return_value=0.0) as now, patch(
            "face.random.random", return_value=0.0
        ), patch("face.random.uniform", return_value=60.0), patch.object(
            face.root, "after", return_value="visitor-timer"
        ) as after:
            for visitor in ("bee", "moth", "butterfly"):
                for direction in (-1, 1):
                    with self.subTest(visitor=visitor, direction=direction), patch(
                        "face.random.choice",
                        side_effect=lambda choices: (
                            direction if choices == (-1, 1) else BIRD_COLORS[0]
                        ),
                    ):
                        now.return_value = 0.0
                        face._visitor_choices = [visitor]
                        face._start_visitor()
                        body = face.canvas.find_withtag(VISITOR_TAG)[2]
                        tick = after.call_args.args[1]
                        positions = []
                        for progress in (0.35, 0.425, 0.5, 0.575, 0.65):
                            now.return_value = VISITOR_FLIGHT_SECONDS * progress
                            tick()
                            left, top, right, bottom = face.canvas.coords(body)
                            positions.append(((left + right) / 2, (top + bottom) / 2))
                        start, first, top, last, end = positions
                        self.assertAlmostEqual(start[0], end[0])
                        self.assertAlmostEqual(start[1], end[1])
                        self.assertGreater(direction * (first[0] - start[0]), 0)
                        self.assertLess(direction * (last[0] - start[0]), 0)
                        self.assertLess(top[1], first[1])
                        self.assertLess(top[1], last[1])
                        now.return_value = VISITOR_FLIGHT_SECONDS
                        tick()
                        self.assertEqual(face.canvas.find_withtag(VISITOR_TAG), ())
                        self.assertEqual(after.call_args.args[1], face._start_visitor)
                        face._visitor_after = None

    def test_birds_never_loop_even_when_random_would_select_one(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        with patch("face.time.monotonic", return_value=0.0) as now, patch(
            "face.random.random", return_value=0.0
        ), patch("face.random.uniform", return_value=60.0), patch.object(
            face.root, "after", return_value="visitor-timer"
        ) as after:
            for direction in (-1, 1):
                with self.subTest(direction=direction), patch(
                    "face.random.choice", side_effect=[direction, BIRD_COLORS[0]]
                ):
                    now.return_value = 0.0
                    face._visitor_choices = ["bird"]
                    face._start_visitor()
                    body = face.canvas.find_withtag(VISITOR_TAG)[2]
                    tick = after.call_args.args[1]
                    for progress in (0.35, 0.425, 0.5, 0.575, 0.65):
                        now.return_value = VISITOR_FLIGHT_SECONDS * progress
                        tick()
                        left, top, right, bottom = face.canvas.coords(body)
                        travel = progress if direction > 0 else 1.0 - progress
                        self.assertAlmostEqual(
                            (left + right) / 2, (-22 + (FACE_WIDTH + 44) * travel) * FACE_SCALE
                        )
                        self.assertAlmostEqual(
                            (top + bottom) / 2,
                            (60 + 6 * math.sin(progress * math.tau * 2))
                            * FACE_SCALE,
                        )
                    now.return_value = VISITOR_FLIGHT_SECONDS
                    tick()
                    self.assertEqual(face.canvas.find_withtag(VISITOR_TAG), ())
                    face._visitor_after = None

    def test_bird_colors_direction_wing_flapping_and_cleanup(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        with patch("face.time.monotonic", return_value=0.0) as now, patch(
            "face.random.random", return_value=1.0
        ), patch("face.random.uniform", return_value=60.0), patch.object(
            face.root, "after", return_value="visitor-timer"
        ) as after:
            for color in BIRD_COLORS:
                for direction in (-1, 1):
                    with self.subTest(color=color, direction=direction), patch(
                        "face.random.choice", side_effect=[direction, color]
                    ) as choice:
                        now.return_value = 0.0
                        face._visitor_choices = ["bird"]
                        face._start_visitor()
                        choice.assert_any_call(BIRD_COLORS)
                        items = face.canvas.find_withtag(VISITOR_TAG)
                        self.assertEqual(face.canvas.itemcget(items[2], "fill"), color)
                        left, _, right, _ = face.canvas.coords(items[2])
                        self.assertGreater((right - left) / FACE_SCALE, 8)
                        tick = after.call_args.args[1]
                        now.return_value = 2.0
                        tick()
                        body = face.canvas.coords(items[2])
                        wing = face.canvas.coords(items[0])
                        head = face.canvas.coords(items[5])
                        self.assertGreater(
                            direction * ((head[0] + head[2]) - (body[0] + body[2])), 0
                        )
                        now.return_value = 2.15
                        tick()
                        next_body = face.canvas.coords(items[2])
                        next_wing = face.canvas.coords(items[0])
                        self.assertNotAlmostEqual(
                            wing[3] - body[1], next_wing[3] - next_body[1]
                        )
                        now.return_value = VISITOR_FLIGHT_SECONDS
                        tick()
                        self.assertEqual(face.canvas.find_withtag(VISITOR_TAG), ())
                        self.assertEqual(after.call_args.args[1], face._start_visitor)
                        face._visitor_after = None

    def test_non_looping_flight_keeps_its_normal_path(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        face._visitor_choices = ["bee"]
        with patch("face.time.monotonic", return_value=0.0) as now, patch(
            "face.random.random", return_value=1.0
        ), patch("face.random.choice", return_value=1), patch(
            "face.random.uniform", return_value=60.0
        ), patch.object(face.root, "after", return_value="visitor-timer") as after:
            face._start_visitor()
            body = face.canvas.find_withtag(VISITOR_TAG)[2]
            tick = after.call_args.args[1]
            now.return_value = VISITOR_FLIGHT_SECONDS / 2
            tick()
            left, top, right, bottom = face.canvas.coords(body)
            self.assertAlmostEqual((left + right) / 2, FACE_WIDTH / 2 * FACE_SCALE)
            self.assertAlmostEqual((top + bottom) / 2, 60.0 * FACE_SCALE)
            face.canvas.delete(VISITOR_TAG)
            face._visitor_after = None

    def test_disabled_animations_cancel_visitor_and_reenable_schedules(self) -> None:
        face = self.face
        face.root.after_cancel(face._visitor_after)
        face._visitor_after = None
        face._start_visitor()
        pending = face._visitor_after
        self.assertTrue(face.canvas.find_withtag(VISITOR_TAG))
        face.set_animations(False)
        self.assertIsNone(face._visitor_after)
        self.assertEqual(face.canvas.find_withtag(VISITOR_TAG), ())
        self.assertNotIn(pending, face.canvas.tk.splitlist(face.canvas.tk.call("after", "info")))
        face.set_animations(True)
        self.assertIsNotNone(face._visitor_after)

    def test_destroy_cancels_visitor_callback(self) -> None:
        pending = self.face._visitor_after
        self.face.canvas.destroy()
        self.assertIsNone(self.face._visitor_after)
        self.assertNotIn(pending, self.root.tk.splitlist(self.root.tk.call("after", "info")))


class EyeAnimationTests(unittest.TestCase):
    def test_loading_opens_lids_and_pauses_blinking_until_finished(self) -> None:
        face = GreenManFace.__new__(GreenManFace)
        face.root = Mock()
        face.animations_enabled = True
        face.loading = False
        face.waiting = False
        face.speaking = False
        face.recording = False
        face.sleeping = False
        face._sleep_transition_started = None
        face._last_activity = 0.0
        face._pupils = [(1, 10.0, 20.0)]
        face._nose_twitch_frame = len(NOSE_TWITCH_OFFSETS)
        face._set_lids = Mock()
        face._coords = Mock()

        blink_intervals = iter([4, 60])

        def randint(low: int, high: int) -> int:
            if (low, high) == (200, 400):
                return 200
            if (low, high) == (40, 100):
                return 1
            self.assertEqual((low, high), (60, 160))
            return next(blink_intervals)

        with patch("face.random.randint", side_effect=randint), patch(
            "face.random.random", return_value=0.9
        ), patch("face.time.monotonic", return_value=0.0):
            face._start_eye_animation()
            tick = face.root.after.call_args.args[1]
            face._set_lids.assert_called_with(BLINK_LID_LEVELS[0])

            face.set_loading(True)
            face._set_lids.assert_called_with(0.0)
            face._set_lids.reset_mock()
            face._coords.reset_mock()
            for _ in range(10):
                tick()
            face._set_lids.assert_not_called()
            self.assertEqual(face._coords.call_count, 10)
            self.assertNotEqual(
                face._coords.call_args_list[0], face._coords.call_args_list[-1]
            )

            face.set_loading(False)
            for _ in range(3):
                tick()
            face._set_lids.assert_not_called()
            tick()
            face._set_lids.assert_called_with(BLINK_LID_LEVELS[0])
            for _ in range(len(BLINK_LID_LEVELS)):
                tick()
            face._set_lids.assert_called_with(0.0)


class NoseAnimationTests(unittest.TestCase):
    def test_twitch_repeats_and_disabling_restores_neutral_nose(self) -> None:
        face = GreenManFace.__new__(GreenManFace)
        face.root = Mock()
        face.animations_enabled = True
        face.loading = False
        face.waiting = False
        face.speaking = True
        face.recording = False
        face.sleeping = False
        face._sleep_transition_started = None
        face._last_activity = 0.0
        face._pupils = []
        face._nose_twitch_frame = len(NOSE_TWITCH_OFFSETS)
        face._set_nose = Mock()
        face._set_lids = Mock()
        face.stop_speaking = Mock()
        face._refresh_eye_color = Mock()

        with patch("face.random.randint", side_effect=[100, 2, 8, 8, 8]), patch(
            "face.time.monotonic", return_value=0.0
        ):
            face._start_eye_animation()
            tick = face.root.after.call_args.args[1]
            face._set_nose.assert_not_called()
            tick()
            face._set_nose.assert_called_with(NOSE_TWITCH_OFFSETS[0])

            face.set_animations(False)
            face._set_nose.assert_called_with(0.0)
            face._set_nose.reset_mock()
            for _ in range(10):
                tick()
            face._set_nose.assert_not_called()

            face.set_animations(True)
            for _ in range(7):
                tick()
            face._set_nose.assert_not_called()
            for _ in range(len(NOSE_TWITCH_OFFSETS)):
                tick()
            self.assertEqual(
                [call.args[0] for call in face._set_nose.call_args_list],
                list(NOSE_TWITCH_OFFSETS),
            )
            tick()
            face._set_nose.assert_called_with(NOSE_TWITCH_OFFSETS[0])

    def test_nose_offset_moves_tip_but_not_bridge(self) -> None:
        face = GreenManFace.__new__(GreenManFace)
        face._nose_item = 1
        face.canvas = Mock()

        face._set_nose(0.0)
        neutral = face.canvas.coords.call_args.args
        face._set_nose(1.0)
        twitch = face.canvas.coords.call_args.args

        self.assertEqual(twitch[:3], neutral[:3])
        for index in range(3, len(neutral), 2):
            self.assertAlmostEqual(twitch[index] - neutral[index], FACE_SCALE)
            self.assertEqual(twitch[index + 1], neutral[index + 1])


class SleepAnimationTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.window = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(self.window.destroy)
        self.clock = patch("face.time.monotonic", return_value=0.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.calendar = patch("face.date")
        self.today = self.calendar.start()
        self.today.today.return_value = date(2026, 2, 15)
        self.addCleanup(self.calendar.stop)
        self.scheduler = Mock()
        self.face = GreenManFace(
            self.scheduler, self.window, COLORS, COLORS["background"]
        )
        self.tick = self.scheduler.after.call_args.args[1]

    def test_speech_pause_preserves_envelope_position_and_glasses(self) -> None:
        self.face.start_speaking([0.0, 1.0, 0.0], window_seconds=1.0)
        mouth_tick = self.face._mouth_tick
        self.assertIsNotNone(mouth_tick)
        self.now.return_value = 0.5
        self.face.set_speech_paused(True)
        self.assertEqual(self.face.mouth_level, 0.0)
        self.assertTrue(self.face.speaking)
        for item in self.face.canvas.find_withtag("reading_glasses"):
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "normal")
        self.now.return_value = 20.5
        self.tick()
        self.assertFalse(self.face.sleeping)
        self.face.set_speech_paused(False)
        self.assertEqual(self.face.mouth_level, 0.0)
        self.now.return_value = 21.3
        assert mouth_tick is not None
        mouth_tick()
        self.assertGreater(self.face.mouth_level, 0.0)
        self.face.stop_speaking()
        self.assertEqual(self.face.mouth_level, 0.0)

    def test_manual_sleep_uses_idle_transition_and_wakes_normally(self) -> None:
        self.now.return_value = 10.0
        self.face.start_sleep_transition()
        self.assertEqual(self.face._sleep_transition_started, 10.0)
        self.now.return_value += SLEEP_BLINK_SECONDS / 2
        self.tick()
        self.assertEqual(self.face.canvas.itemcget(self.face._lids[0][0], "state"), "normal")
        self.now.return_value = 10.0 + SLEEP_BLINK_COUNT * SLEEP_BLINK_SECONDS
        self.now.return_value += SLEEP_YAWN_SECONDS / 2
        self.tick()
        self.assertAlmostEqual(self.face.mouth_level, 1.0)
        self.now.return_value = 10.0 + SLEEP_BLINK_COUNT * SLEEP_BLINK_SECONDS
        self.now.return_value += SLEEP_YAWN_SECONDS + 0.01
        self.tick()
        self.assertTrue(self.face.sleeping)
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "normal"
            for item in self.face.canvas.find_withtag("nightcap")
        ))
        self.face.start_sleep_transition()
        self.assertTrue(self.face.sleeping)
        self.face.note_activity()
        self.assertFalse(self.face.sleeping)

    def test_manual_sleep_respects_active_states_and_disabled_animations(self) -> None:
        for state in ("loading", "waiting", "recording", "speaking"):
            with self.subTest(state=state):
                setattr(self.face, state, True)
                self.face.start_sleep_transition()
                self.assertIsNone(self.face._sleep_transition_started)
                setattr(self.face, state, False)
        self.face.set_animations(False)
        self.face.start_sleep_transition()
        self.assertIsNone(self.face._sleep_transition_started)
        self.face.set_animations(True)
        self.face.start_sleep_transition()
        started = self.face._sleep_transition_started
        self.now.return_value += 1
        self.face.start_sleep_transition()
        self.assertEqual(self.face._sleep_transition_started, started)

    def test_idle_threshold_sleep_animation_and_wake(self) -> None:
        cap = self.face.canvas.find_withtag("nightcap")
        self.assertGreater(len(cap), 2)
        pom = self.face.canvas.find_withtag("nightcap_pom")
        self.assertEqual(len(pom), 10)
        self.assertEqual(self.face.canvas.itemcget(cap[0], "fill"), "#8cbd3c")
        self.assertEqual(self.face.canvas.itemcget(cap[1], "fill"), "#b9dd83")
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "fill") == "#d0ed9e" for item in pom
        ))
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "hidden" for item in cap
        ))
        self.now.return_value = SLEEP_IDLE_SECONDS - 0.01
        self.tick()
        self.assertFalse(self.face.sleeping)
        self.now.return_value = SLEEP_IDLE_SECONDS
        self.tick()
        self.assertFalse(self.face.sleeping)
        self.assertEqual(self.face._sleep_transition_started, SLEEP_IDLE_SECONDS)
        lid = self.face._lids[0][0]
        for blink in range(SLEEP_BLINK_COUNT):
            self.now.return_value = (
                SLEEP_IDLE_SECONDS + (blink + 0.5) * SLEEP_BLINK_SECONDS
            )
            self.tick()
            self.assertEqual(self.face.canvas.itemcget(lid, "state"), "normal")
            top, bottom = self.face.canvas.coords(lid)[1::2]
            self.assertAlmostEqual(bottom - top, 7 * FACE_SCALE)
            self.now.return_value = (
                SLEEP_IDLE_SECONDS + (blink + 1) * SLEEP_BLINK_SECONDS
            )
            self.tick()
            if blink < SLEEP_BLINK_COUNT - 1:
                self.assertEqual(self.face.canvas.itemcget(lid, "state"), "hidden")
            self.assertFalse(self.face.sleeping)
        yawn_start = SLEEP_IDLE_SECONDS + SLEEP_BLINK_COUNT * SLEEP_BLINK_SECONDS
        self.now.return_value = yawn_start + 0.01
        self.tick()
        for lid, _, _ in self.face._lids:
            self.assertEqual(self.face.canvas.itemcget(lid, "state"), "normal")
            top, bottom = self.face.canvas.coords(lid)[1::2]
            self.assertAlmostEqual(bottom - top, 7 * FACE_SCALE / 2)
        self.now.return_value = yawn_start + SLEEP_YAWN_SECONDS / 4
        self.tick()
        self.assertAlmostEqual(self.face.mouth_level, 0.5)
        self.now.return_value = yawn_start + SLEEP_YAWN_SECONDS / 2
        self.tick()
        self.assertAlmostEqual(self.face.mouth_level, 1.0)
        self.assertFalse(self.face.sleeping)
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "hidden" for item in cap
        ))
        for item in self.face._sleep_zs:
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")
        self.now.return_value = yawn_start + SLEEP_YAWN_SECONDS * 0.75
        self.tick()
        self.assertAlmostEqual(self.face.mouth_level, 0.5)
        for lid, _, _ in self.face._lids:
            self.assertEqual(self.face.canvas.itemcget(lid, "state"), "normal")
            top, bottom = self.face.canvas.coords(lid)[1::2]
            self.assertAlmostEqual(bottom - top, 7 * FACE_SCALE / 2)
        self.now.return_value = yawn_start + SLEEP_YAWN_SECONDS + 0.01
        self.tick()
        self.assertTrue(self.face.sleeping)
        self.assertEqual(self.face.mouth_level, 0.0)
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "normal" for item in cap
        ))
        x1, y1, x2, y2 = self.face.canvas.bbox("nightcap")
        px1, py1, px2, py2 = self.face.canvas.bbox("nightcap_pom")
        self.assertGreater(px2 - px1, 16 * FACE_SCALE)
        self.assertGreater(py2 - py1, 18 * FACE_SCALE)
        self.assertGreaterEqual(x1, 0)
        self.assertGreaterEqual(y1, 0)
        self.assertLessEqual(x2, round(FACE_WIDTH * FACE_SCALE))
        self.assertLessEqual(y2, round(FACE_HEIGHT * FACE_SCALE))
        self.assertLess(y2, min(self.face.canvas.coords(eye)[1] for eye in self.face._eyes))
        for lid, _, _ in self.face._lids:
            self.assertEqual(self.face.canvas.itemcget(lid, "state"), "normal")
            top, bottom = self.face.canvas.coords(lid)[1::2]
            self.assertAlmostEqual(bottom - top, 7 * FACE_SCALE)
        for item in self.face._sleep_zs:
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "normal")
        before = self.face.canvas.coords(self.face._sleep_zs[0])
        self.now.return_value += 0.4
        self.tick()
        after = self.face.canvas.coords(self.face._sleep_zs[0])
        self.assertGreater(after[0], before[0])
        self.assertLess(after[1], before[1])

        self.face.note_activity()
        self.assertFalse(self.face.sleeping)
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "hidden" for item in cap
        ))
        for lid, _, _ in self.face._lids:
            self.assertEqual(self.face.canvas.itemcget(lid, "state"), "hidden")
        for item in self.face._sleep_zs:
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")
        self.now.return_value += SLEEP_IDLE_SECONDS - 0.01
        self.tick()
        self.assertFalse(self.face.sleeping)
        self.now.return_value += 0.01
        self.tick()
        self.assertIsNotNone(self.face._sleep_transition_started)

    def test_seasonal_hats_follow_local_month_even_while_sleeping(self) -> None:
        self.today.today.return_value = date(2026, 11, 1)
        self._fall_asleep()
        cap = self.face.canvas.find_withtag("nightcap")
        hat = self.face.canvas.find_withtag("pilgrim_hat")
        santa = self.face.canvas.find_withtag("santa_hat")
        party = self.face.canvas.find_withtag("party_hat")
        sequins = self.face.canvas.find_withtag("party_sequin")
        bunny = self.face.canvas.find_withtag("bunny_ears")
        uncle_sam = self.face.canvas.find_withtag("uncle_sam_hat")
        jack = self.face.canvas.find_withtag("jack_o_lantern")
        horns = self.face.canvas.find_withtag("devil_horns")
        grooves = self.face.canvas.find_withtag("jack_groove")
        candle = self.face.canvas.find_withtag("jack_candle")
        antlers = self.face.canvas.find_withtag("reindeer_antlers")
        red = self.face.canvas.find_withtag("santa_red")
        buckle = self.face.canvas.find_withtag("pilgrim_buckle")
        self.assertTrue(hat)
        self.assertEqual(len(sequins), 10)
        self.assertTrue(set(sequins).issubset(party))
        self.assertGreater(len({self.face.canvas.itemcget(item, "fill") for item in sequins}), 1)
        self.assertEqual(len(bunny), 4)
        self.assertTrue(uncle_sam)
        self.assertEqual(len(horns), 2)
        self.assertTrue(set(horns).issubset(jack))
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "fill") == "#d42d35" for item in horns
        ))
        self.assertEqual(len(grooves), 5)
        self.assertTrue(set(grooves).issubset(jack))
        self.assertTrue(all(
            self.face.canvas.type(item) == "line"
            and self.face.canvas.itemcget(item, "smooth") != "0"
            for item in grooves
        ))
        self.assertLess(max(grooves), min(self.face.canvas.find_withtag("jack_glow")))
        self.assertEqual(len(candle), 2)
        self.assertTrue(set(candle).issubset(jack))
        self.assertEqual(self.face.canvas.itemcget(candle[0], "fill"), "#fff1c1")
        self.assertEqual(self.face.canvas.itemcget(candle[1], "fill"), "#ffdf4f")
        self.assertEqual(len(self.face.canvas.find_withtag("jack_glow")), 2)
        self.assertEqual(
            {self.face.canvas.itemcget(item, "fill") for item in bunny},
            {"#faf8ef", "#efa3b6"},
        )
        self.assertTrue(
            {"#faf8ef", "#c92735", "#244b91"}.issubset(
                {self.face.canvas.itemcget(item, "fill") for item in uncle_sam}
            )
        )
        self.assertEqual(len(antlers), 6)
        self.assertEqual(len(red), 1)
        self.assertEqual(self.face.canvas.itemcget(red[0], "fill"), "#c92735")
        self.assertEqual(len(buckle), 1)
        self.assertEqual(self.face.canvas.itemcget(hat[0], "fill"), "#171717")
        self.assertEqual(self.face.canvas.itemcget(buckle[0], "outline"), "#c0c0c0")
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "normal" for item in hat
        ))
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "hidden" for item in cap
        ))
        x1, y1, x2, y2 = self.face.canvas.bbox("pilgrim_hat")
        self.assertGreaterEqual(x1, 0)
        self.assertGreaterEqual(y1, 0)
        self.assertLessEqual(x2, round(FACE_WIDTH * FACE_SCALE))
        self.assertLess(y2, min(self.face.canvas.coords(eye)[1] for eye in self.face._eyes))
        for month in range(1, 13):
            with self.subTest(month=month):
                self.today.today.return_value = date(2026, month, 15)
                self.tick()
                outfits = {1: party, 4: bunny, 7: uncle_sam, 10: jack, 11: hat, 12: santa}
                for outfit_month, items in outfits.items():
                    for item in items:
                        self.assertEqual(
                            self.face.canvas.itemcget(item, "state"),
                            "normal" if month == outfit_month else "hidden",
                        )
                for item in cap:
                    self.assertEqual(
                        self.face.canvas.itemcget(item, "state"),
                        "hidden" if month in outfits else "normal",
                    )
                if month in (1, 4, 7, 10):
                    tag = {
                        1: "party_hat", 4: "bunny_ears",
                        7: "uncle_sam_hat", 10: "jack_o_lantern",
                    }[month]
                    x1, y1, x2, y2 = self.face.canvas.bbox(tag)
                    self.assertGreaterEqual(x1, 0)
                    self.assertGreaterEqual(y1, 0)
                    self.assertLessEqual(x2, round(FACE_WIDTH * FACE_SCALE))
                    self.assertLess(
                        y2, min(self.face.canvas.coords(eye)[1] for eye in self.face._eyes)
                    )
        x1, y1, x2, y2 = self.face.canvas.bbox("santa_hat")
        self.assertGreaterEqual(x1, 0)
        self.assertGreaterEqual(y1, 0)
        self.assertLessEqual(x2, round(FACE_WIDTH * FACE_SCALE))
        self.assertLess(y2, min(self.face.canvas.coords(eye)[1] for eye in self.face._eyes))
        self.tick()
        self.face.note_activity()
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "hidden"
            for item in (*cap, *hat, *santa, *party, *bunny, *uncle_sam, *jack)
        ))
        self._fall_asleep()
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "normal" for item in santa
        ))
        self.face.set_animations(False)
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "hidden"
            for item in (*cap, *hat, *santa, *party, *bunny, *uncle_sam, *jack)
        ))

    def test_january_party_hat_disappears_on_wake_and_animation_disable(self) -> None:
        self.today.today.return_value = date(2026, 1, 15)
        party = self.face.canvas.find_withtag("party_hat")
        self._fall_asleep()
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "normal" for item in party
        ))
        self.face.note_activity()
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "hidden" for item in party
        ))
        self._fall_asleep()
        self.face.set_animations(False)
        self.assertTrue(all(
            self.face.canvas.itemcget(item, "state") == "hidden" for item in party
        ))

    def test_activity_interrupts_blinks_and_yawn(self) -> None:
        for elapsed in (SLEEP_BLINK_SECONDS / 2,
                        SLEEP_BLINK_COUNT * SLEEP_BLINK_SECONDS + SLEEP_YAWN_SECONDS / 2):
            with self.subTest(elapsed=elapsed):
                self.now.return_value += SLEEP_IDLE_SECONDS
                self.tick()
                self.now.return_value += elapsed
                self.tick()
                self.face.note_activity()
                self.assertIsNone(self.face._sleep_transition_started)
                self.assertFalse(self.face.sleeping)
                for item in self.face.canvas.find_withtag("nightcap"):
                    self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")
                self.assertEqual(self.face.mouth_level, 0.0)
                for lid, _, _ in self.face._lids:
                    self.assertEqual(self.face.canvas.itemcget(lid, "state"), "hidden")
                for item in self.face._sleep_zs:
                    self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")
                self.now.return_value += SLEEP_IDLE_SECONDS - 0.01
                self.tick()
                self.assertIsNone(self.face._sleep_transition_started)

    def _fall_asleep(self) -> None:
        self.now.return_value += SLEEP_IDLE_SECONDS
        self.tick()
        self.now.return_value += (
            SLEEP_BLINK_COUNT * SLEEP_BLINK_SECONDS + SLEEP_YAWN_SECONDS + 0.01
        )
        self.tick()
        self.assertTrue(self.face.sleeping)

    def test_active_states_interrupt_yawn(self) -> None:
        for start, stop in (
            (lambda: self.face.set_loading(True), lambda: self.face.set_loading(False)),
            (lambda: self.face.set_waiting(True), lambda: self.face.set_waiting(False)),
            (
                lambda: self.face.set_recording(True),
                lambda: self.face.set_recording(False),
            ),
            (lambda: self.face.start_speaking(None), self.face.stop_speaking),
        ):
            with self.subTest(start=start):
                self.now.return_value += SLEEP_IDLE_SECONDS
                self.tick()
                self.now.return_value += (
                    SLEEP_BLINK_COUNT * SLEEP_BLINK_SECONDS + SLEEP_YAWN_SECONDS / 2
                )
                self.tick()
                self.assertAlmostEqual(self.face.mouth_level, 1.0)
                start()
                self.assertIsNone(self.face._sleep_transition_started)
                self.assertFalse(self.face.sleeping)
                if not self.face.speaking:
                    self.assertEqual(self.face.mouth_level, 0.0)
                self.now.return_value += SLEEP_YAWN_SECONDS
                self.tick()
                self.assertFalse(self.face.sleeping)
                self.assertIsNone(self.face._sleep_transition_started)
                stop()

    def test_active_states_wake_and_restart_idle_countdown(self) -> None:
        for start, stop in (
            (lambda: self.face.set_loading(True), lambda: self.face.set_loading(False)),
            (lambda: self.face.set_waiting(True), lambda: self.face.set_waiting(False)),
            (
                lambda: self.face.set_recording(True),
                lambda: self.face.set_recording(False),
            ),
            (lambda: self.face.start_speaking(None), self.face.stop_speaking),
        ):
            with self.subTest(start=start):
                self._fall_asleep()
                for item in self.face.canvas.find_withtag("nightcap"):
                    self.assertEqual(self.face.canvas.itemcget(item, "state"), "normal")
                start()
                self.assertFalse(self.face.sleeping)
                for item in self.face.canvas.find_withtag("nightcap"):
                    self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")
                self.now.return_value += SLEEP_IDLE_SECONDS + 1
                self.tick()
                self.assertFalse(self.face.sleeping)
                stop()
                self.now.return_value += SLEEP_IDLE_SECONDS - 0.01
                self.tick()
                self.assertFalse(self.face.sleeping)

    def test_disabling_animations_wakes_and_prevents_sleep(self) -> None:
        self._fall_asleep()
        self.face.set_animations(False)
        self.assertFalse(self.face.sleeping)
        for item in self.face.canvas.find_withtag("nightcap"):
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")
        for item in self.face._sleep_zs:
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")
        self.now.return_value += SLEEP_IDLE_SECONDS * 2
        self.tick()
        self.assertFalse(self.face.sleeping)
        self.face.set_animations(True)
        self.now.return_value += SLEEP_IDLE_SECONDS - 0.01
        self.tick()
        self.assertFalse(self.face.sleeping)
        self.now.return_value += 0.01
        self.tick()
        self.assertIsNotNone(self.face._sleep_transition_started)

    def test_disabling_animations_during_yawn_restores_neutral_face(self) -> None:
        self.now.return_value = SLEEP_IDLE_SECONDS
        self.tick()
        self.now.return_value += (
            SLEEP_BLINK_COUNT * SLEEP_BLINK_SECONDS + SLEEP_YAWN_SECONDS / 2
        )
        self.tick()
        self.assertAlmostEqual(self.face.mouth_level, 1.0)
        self.face.set_animations(False)
        self.assertIsNone(self.face._sleep_transition_started)
        self.assertEqual(self.face.mouth_level, 0.0)
        self.now.return_value += SLEEP_IDLE_SECONDS
        self.tick()
        self.assertFalse(self.face.sleeping)
        self.assertIsNone(self.face._sleep_transition_started)


class EyeLegendTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.legend = EyeLegend(self.root, COLORS, COLORS["background"])
        self.legend.frame.pack()
        self.root.update_idletasks()

    def tearDown(self) -> None:
        self.root.destroy()

    def test_examples_are_compact_and_show_expected_eye_colors(self) -> None:
        self.assertLess(self.legend.frame.winfo_reqwidth(), 150)
        self.assertLess(self.legend.frame.winfo_reqheight(), 160)
        expected = {
            "loading": COLORS["green_selected"],
            "waiting": WAITING_EYE_COLOR,
            "recording": RECORDING_EYE_COLOR,
            "idle": COLORS["green_selected"],
            "speaking": COLORS["green_selected"],
            "sleeping": COLORS["green"],
        }
        self.assertEqual(set(self.legend._pupils), set(expected))
        for name, color in expected.items():
            canvas, _ = self.legend._pupils[name]
            self.assertEqual(canvas.itemcget(canvas.find_all()[0], "fill"), color)

    def test_speaking_example_shows_transparent_glasses_frame(self) -> None:
        canvas, pupil = self.legend._pupils["speaking"]
        frames = canvas.find_withtag("reading_glasses")
        self.assertEqual(len(frames), 1)
        frame = frames[0]
        self.assertEqual(canvas.itemcget(frame, "outline"), GLASSES_COLOR)
        self.assertEqual(canvas.itemcget(frame, "fill"), "")
        self.assertAlmostEqual(float(canvas.itemcget(frame, "width")), GLASSES_WIDTH)
        fx1, fy1, fx2, fy2 = canvas.coords(frame)
        px1, py1, px2, py2 = canvas.coords(pupil)
        self.assertLess(fx1, px1)
        self.assertLess(fy1, py1)
        self.assertGreater(fx2, px2)
        self.assertGreater(fy2, py2)
        for enabled in (False, True):
            self.legend.set_animations(enabled)
            self.assertNotEqual(canvas.itemcget(frame, "state"), "hidden")

    def test_examples_move_and_animation_setting_stops_and_resumes_them(self) -> None:
        def coords(name: str) -> list[float]:
            canvas, pupil = self.legend._pupils[name]
            return canvas.coords(pupil)

        before = {name: coords(name) for name in self.legend._pupils}
        self.root.after(150, self.root.quit)
        self.root.mainloop()
        for name in ("loading", "waiting", "idle"):
            self.assertNotEqual(coords(name), before[name])
        for name in ("recording", "speaking", "sleeping"):
            self.assertEqual(coords(name), before[name])

        self.legend.set_animations(False)
        self.assertIsNone(self.legend._after)
        for name in ("loading", "waiting", "idle"):
            self.assertEqual(coords(name), [9.0, 5.0, 15.0, 11.0])
        phase = self.legend._phase
        self.root.after(100, self.root.quit)
        self.root.mainloop()
        self.assertEqual(self.legend._phase, phase)

        self.legend.set_animations(True)
        self.assertIsNotNone(self.legend._after)
        self.assertGreater(self.legend._phase, phase)

    def test_loading_circles_and_waiting_sweeps_in_both_directions(self) -> None:
        positions: dict[str, list[tuple[float, float]]] = {
            "loading": [],
            "waiting": [],
        }
        for _ in range(60):
            self.legend.frame.after_cancel(self.legend._after)
            self.legend._tick()
            for name, points in positions.items():
                canvas, pupil = self.legend._pupils[name]
                x1, y1, x2, y2 = canvas.coords(pupil)
                points.append(((x1 + x2) / 2 - 12, (y1 + y2) / 2 - 8))

        for name in positions:
            xs = [x for x, _ in positions[name]]
            self.assertLess(min(xs), -2)
            self.assertGreater(max(xs), 2)
        loading_y = [y for _, y in positions["loading"]]
        self.assertLess(min(loading_y), -1)
        self.assertGreater(max(loading_y), 1)
        self.assertTrue(all(y == 0 for _, y in positions["waiting"]))

    def test_destroy_cancels_pending_animation(self) -> None:
        scheduled = self.legend._after
        self.assertIsNotNone(scheduled)
        self.legend.frame.destroy()
        self.assertIsNone(self.legend._after)
        self.assertNotIn(scheduled, self.root.tk.splitlist(self.root.tk.call("after", "info")))


class GreenManFaceTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.face = GreenManFace(self.root, self.root, COLORS, COLORS["background"])

    def tearDown(self) -> None:
        if self.face._eye_after is not None:
            self.root.after_cancel(self.face._eye_after)
        if self.face._mouth_after is not None:
            self.root.after_cancel(self.face._mouth_after)
        self.root.destroy()

    def test_speaking_opens_mouth_and_stopping_closes_it(self) -> None:
        closed_height = self.face.mouth_level
        self.face.start_speaking([1.0] * 200)
        for _ in range(30):
            self.root.update()
            self.root.after(33)
        self.assertTrue(self.face.speaking)
        self.assertGreater(self.face.mouth_level, closed_height)
        self.face.stop_speaking()
        self.assertFalse(self.face.speaking)
        self.assertEqual(self.face.mouth_level, 0.0)

    def test_reading_glasses_show_only_during_speech(self) -> None:
        glasses = self.face.canvas.find_withtag("reading_glasses")
        self.assertEqual(len(glasses), 5)
        lenses = [item for item in glasses if self.face.canvas.type(item) == "oval"]
        self.assertEqual(len(lenses), 2)
        for item in glasses:
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")
            color_option = "outline" if item in lenses else "fill"
            self.assertEqual(self.face.canvas.itemcget(item, color_option), GLASSES_COLOR)
            self.assertAlmostEqual(
                float(self.face.canvas.itemcget(item, "width")), GLASSES_WIDTH
            )
        for lens in lenses:
            self.assertEqual(self.face.canvas.itemcget(lens, "fill"), "")

        self.face.start_speaking(None)
        for item in glasses:
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "normal")
        for lens, (pupil, _, _) in zip(lenses, self.face._pupils):
            lx1, ly1, lx2, ly2 = self.face.canvas.coords(lens)
            px1, py1, px2, py2 = self.face.canvas.coords(pupil)
            self.assertLess(lx1, px1)
            self.assertLess(ly1, py1)
            self.assertGreater(lx2, px2)
            self.assertGreater(ly2, py2)

        self.face.set_recording(True)
        for eye in self.face._eyes:
            self.assertEqual(
                self.face.canvas.itemcget(eye, "fill"), RECORDING_EYE_COLOR
            )
        self.face.stop_speaking()
        for item in glasses:
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")

        self.face.start_speaking(None)
        self.face.set_animations(False)
        for item in glasses:
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")
        self.face.start_speaking(None)
        for item in glasses:
            self.assertEqual(self.face.canvas.itemcget(item, "state"), "hidden")

    def test_pupils_center_while_speaking(self) -> None:
        self.face.start_speaking(None)
        for _ in range(40):
            self.root.update()
            self.root.after(40)
        pupil, eye_x, eye_y = self.face._pupils[0]
        x1, y1, x2, y2 = self.face.canvas.coords(pupil)
        self.assertAlmostEqual((x1 + x2) / 2, eye_x * FACE_SCALE, delta=0.5)
        self.assertAlmostEqual((y1 + y2) / 2, eye_y * FACE_SCALE, delta=0.5)
        self.face.stop_speaking()

    def test_eyes_blink_and_reopen(self) -> None:
        lid = self.face._lids[0][0]
        states = set()
        for _ in range(400):
            self.root.update()
            states.add(self.face.canvas.itemcget(lid, "state"))
            self.root.after(40)
            if {"normal", "hidden"} <= states:
                break
        self.assertEqual(states, {"normal", "hidden"})


if __name__ == "__main__":
    unittest.main()
