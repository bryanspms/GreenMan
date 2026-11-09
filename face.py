"""Animated Green Man face drawn on a Tkinter canvas."""

from __future__ import annotations

import math
import random
import time
import tkinter as tk
from collections.abc import Callable, Mapping

FACE_WIDTH = 130
FACE_HEIGHT = 130
# One inch (96 px) of extra height on top of the 130 px design size.
FACE_SCALE = (FACE_HEIGHT + 96) / FACE_HEIGHT
MOUTH_FRAME_MS = 33
EYE_FRAME_MS = 40
SLEEP_IDLE_SECONDS = 60.0
SLEEP_BLINK_COUNT = 3
SLEEP_BLINK_SECONDS = 1.2
SLEEP_YAWN_SECONDS = 2.4
SLEEP_Z_CYCLE_SECONDS = 2.4
MOUTH_SYNC_LATENCY_SECONDS = 0.08
EYE_HEIGHT = 7
WAITING_EYE_COLOR = "#ffd800"
RECORDING_EYE_COLOR = "#e02020"
GLASSES_COLOR = "#f4d28a"
GLASSES_WIDTH = 1.6
LOADING_RADIUS = 4.5
LOADING_RADIANS_PER_TICK = 0.25
WAITING_SWEEP = 4.5
WAITING_SWEEP_TICKS = 12
BLINK_LID_LEVELS = (0.55, 1.0, 1.0, 0.55)
NOSE_TWITCH_OFFSETS = (0.5, 1.0, 0.5, 0.0, -0.5, -1.0, -0.5, 0.0)


class EyeLegend:
    """Small animated examples of the face's eye states."""

    def __init__(
        self, parent: tk.Misc, colors: Mapping[str, str], background: str
    ) -> None:
        self.frame = tk.Frame(parent, bg=background)
        self.frame.bind("<Destroy>", self._on_destroy, add="+")
        tk.Label(
            self.frame, text="Eye guide", font=("TkDefaultFont", 9, "bold"),
            fg=colors["text"], bg=background,
        ).pack(anchor=tk.W)
        self._pupils: dict[str, tuple[tk.Canvas, int]] = {}
        for key, label, fill in (
            ("loading", "Loading model", colors["green_selected"]),
            ("waiting", "Waiting for reply", WAITING_EYE_COLOR),
            ("recording", "Mic recording", RECORDING_EYE_COLOR),
            ("idle", "Idle", colors["green_selected"]),
            ("speaking", "Speaking", colors["green_selected"]),
            ("sleeping", "Sleeping", colors["green"]),
        ):
            row = tk.Frame(self.frame, bg=background)
            row.pack(anchor=tk.W)
            canvas = tk.Canvas(
                row, width=24, height=16, bg=background, highlightthickness=0
            )
            canvas.pack(side=tk.LEFT)
            canvas.create_oval(2, 4, 22, 12, fill=fill, outline=colors["text"])
            pupil = canvas.create_oval(9, 5, 15, 11, fill=colors["text"], outline="")
            if key == "sleeping":
                canvas.itemconfigure(pupil, state=tk.HIDDEN)
            elif key == "speaking":
                canvas.create_oval(
                    1, 2, 23, 14, fill="", outline=GLASSES_COLOR,
                    width=GLASSES_WIDTH, tags="reading_glasses",
                )
            self._pupils[key] = (canvas, pupil)
            tk.Label(
                row, text=label, font=("TkDefaultFont", 9),
                fg=colors["text"], bg=background,
            ).pack(side=tk.LEFT, padx=(4, 0))
        self._after: str | None = None
        self._enabled = False
        self._phase = 0
        self._waiting_x = 0.0
        self.set_animations(True)

    def set_animations(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if enabled:
            self._tick()
        else:
            if self._after is not None:
                self.frame.after_cancel(self._after)
                self._after = None
            self._waiting_x = 0.0
            for key in ("loading", "waiting", "idle"):
                self._move_pupil(key, 0.0, 0.0)

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self.frame and self._after is not None:
            self.frame.after_cancel(self._after)
            self._after = None

    def _move_pupil(self, key: str, x: float, y: float) -> None:
        canvas, pupil = self._pupils[key]
        canvas.coords(pupil, 9 + x, 5 + y, 15 + x, 11 + y)

    def _tick(self) -> None:
        self._phase += 1
        angle = self._phase * LOADING_RADIANS_PER_TICK
        self._move_pupil("loading", 3 * math.cos(angle), 2 * math.sin(angle))
        direction = 1 if (self._phase // WAITING_SWEEP_TICKS) % 2 == 0 else -1
        self._waiting_x += (direction * 4 - self._waiting_x) * 0.35
        self._move_pupil("waiting", self._waiting_x, 0.0)
        self._move_pupil("idle", 2.5 * math.sin(self._phase / 24), 0.0)
        self._after = self.frame.after(EYE_FRAME_MS, self._tick)


class GreenManFace:
    """A leafy face whose eyes wander and whose mouth and brows follow speech."""

    def __init__(
        self,
        root: tk.Misc,
        parent: tk.Misc,
        colors: Mapping[str, str],
        background: str,
    ) -> None:
        self.root = root
        self.colors = colors
        self.background = background
        self.canvas = tk.Canvas(
            parent,
            width=round(FACE_WIDTH * FACE_SCALE),
            height=round(FACE_HEIGHT * FACE_SCALE),
            highlightthickness=0,
            bg=background,
        )
        self.speaking = False
        self.waiting = False
        self.loading = False
        self.animations_enabled = True
        self.recording = False
        self.sleeping = False
        self._last_activity = time.monotonic()
        self._sleep_transition_started: float | None = None
        self._sleep_started = 0.0
        self._eyes: list[int] = []
        self.mouth_level = 0.0
        self._mouth_after: str | None = None
        self._mouth_tick: Callable[[], None] | None = None
        self._mouth_pause_started: float | None = None
        self._mouth_paused_seconds = 0.0
        self._eye_after: str | None = None
        self._nose_twitch_frame = len(NOSE_TWITCH_OFFSETS)
        self._pupils: list[tuple[int, float, float]] = []
        self._brows: list[tuple[int, float, float]] = []
        self._lids: list[tuple[int, float, float]] = []
        self._draw()
        self._sleep_zs = [
            self.canvas.create_text(
                0, 0, text="Z", fill=self.colors["text"],
                font=("TkDefaultFont", 10, "bold"), state=tk.HIDDEN,
            )
            for _ in range(3)
        ]
        self.canvas.scale("all", 0, 0, FACE_SCALE, FACE_SCALE)
        self._start_eye_animation()

    def start_speaking(
        self, envelope: list[float] | None, window_seconds: float = 0.04
    ) -> None:
        """Animate the mouth from an audio envelope, or flap it if none."""
        self.stop_speaking()
        if not self.animations_enabled:
            return
        self.note_activity()
        self.speaking = True
        self.canvas.itemconfigure("reading_glasses", state=tk.NORMAL)
        started_at = time.monotonic() + MOUTH_SYNC_LATENCY_SECONDS
        phase = 0
        brow_lifts = [0.0, 0.0]
        emphasis = [0.0, 0.0]
        ticks_until_emphasis = 15

        def tick() -> None:
            nonlocal phase, ticks_until_emphasis
            phase += 1
            if envelope is not None:
                index = int(
                    (time.monotonic() - started_at - self._mouth_paused_seconds)
                    / window_seconds
                )
                target = envelope[index] if 0 <= index < len(envelope) else 0.0
            else:
                target = 0.5 + 0.5 * math.sin(phase * 0.9)
            rate = 0.6 if target > self.mouth_level else 0.3
            self._set_mouth(self.mouth_level + (target - self.mouth_level) * rate)

            ticks_until_emphasis -= 1
            if ticks_until_emphasis <= 0 and target > 0.4:
                strength = random.uniform(0.5, 1.0)
                favored = random.randint(0, 1)
                emphasis[favored] = strength
                emphasis[1 - favored] = strength * random.uniform(0.3, 1.0)
                ticks_until_emphasis = random.randint(15, 45)
            for side in (0, 1):
                goal = min(1.0, 0.25 * target + emphasis[side])
                brow_lifts[side] += (goal - brow_lifts[side]) * 0.3
                emphasis[side] *= 0.88
            self._set_brows((brow_lifts[0], brow_lifts[1]))
            self._mouth_after = self.root.after(MOUTH_FRAME_MS, tick)

        self._mouth_tick = tick
        tick()

    def set_speech_paused(self, paused: bool) -> None:
        """Pause the mouth animation without losing its place in the envelope."""
        if not self.speaking or self._mouth_tick is None:
            return
        if paused and self._mouth_pause_started is None:
            self._mouth_pause_started = time.monotonic()
            if self._mouth_after is not None:
                self.root.after_cancel(self._mouth_after)
                self._mouth_after = None
            self._set_mouth(0.0)
            self._set_brows((0.0, 0.0))
        elif not paused and self._mouth_pause_started is not None:
            self._mouth_paused_seconds += time.monotonic() - self._mouth_pause_started
            self._mouth_pause_started = None
            self._mouth_tick()

    def set_waiting(self, waiting: bool) -> None:
        """Turn the eyes yellow and sweep them side to side while waiting."""
        if self.waiting != waiting:
            self.note_activity()
        self.waiting = waiting
        self._refresh_eye_color()

    def set_recording(self, recording: bool) -> None:
        """Turn the eyes red while the microphone is recording."""
        if self.recording != recording:
            self.note_activity()
        self.recording = recording
        self._refresh_eye_color()

    def set_animations(self, enabled: bool) -> None:
        """Show or hide all animation; a disabled face stays still and neutral."""
        if self.animations_enabled != enabled:
            self.note_activity()
        self.animations_enabled = enabled
        if not enabled:
            self.stop_speaking()
            self._set_lids(0.0)
            self._set_nose(0.0)
            self._nose_twitch_frame = len(NOSE_TWITCH_OFFSETS)
            for pupil, eye_x, eye_y in self._pupils:
                self._coords(pupil, eye_x - 2.5, eye_y - 3, eye_x + 2.5, eye_y + 3)
        self._refresh_eye_color()

    def _refresh_eye_color(self) -> None:
        if not self.animations_enabled:
            fill = self.colors["green_selected"]
        elif self.recording:
            fill = RECORDING_EYE_COLOR
        elif self.waiting:
            fill = WAITING_EYE_COLOR
        else:
            fill = self.colors["green_selected"]
        for eye in self._eyes:
            self.canvas.itemconfigure(eye, fill=fill)

    def set_loading(self, loading: bool) -> None:
        """Roll the pupils without blinking while a model loads."""
        if self.loading != loading:
            self.note_activity()
        self.loading = loading
        if loading:
            self._set_lids(0.0)

    def stop_speaking(self) -> None:
        if self.speaking:
            self.note_activity()
        if self._mouth_after is not None:
            self.root.after_cancel(self._mouth_after)
            self._mouth_after = None
        self.speaking = False
        self._mouth_tick = None
        self._mouth_pause_started = None
        self._mouth_paused_seconds = 0.0
        self.canvas.itemconfigure("reading_glasses", state=tk.HIDDEN)
        self._set_mouth(0.0)
        self._set_brows((0.0, 0.0))

    def note_activity(self) -> None:
        """Wake the face and restart the idle countdown."""
        self._last_activity = time.monotonic()
        if self._sleep_transition_started is not None:
            self._sleep_transition_started = None
            self._set_lids(0.0)
            self._set_mouth(0.0)
        if self.sleeping:
            self.sleeping = False
            self._set_lids(0.0)
            self.canvas.itemconfigure("nightcap", state=tk.HIDDEN)
            for item in self._sleep_zs:
                self.canvas.itemconfigure(item, state=tk.HIDDEN)

    def _animate_sleep_transition(self, now: float) -> None:
        assert self._sleep_transition_started is not None
        elapsed = now - self._sleep_transition_started
        blink_duration = SLEEP_BLINK_COUNT * SLEEP_BLINK_SECONDS
        if elapsed < blink_duration:
            phase = (elapsed % SLEEP_BLINK_SECONDS) / SLEEP_BLINK_SECONDS
            self._set_lids((1.0 - math.cos(2 * math.pi * phase)) / 2)
        elif elapsed < blink_duration + SLEEP_YAWN_SECONDS:
            phase = (elapsed - blink_duration) / SLEEP_YAWN_SECONDS
            self._set_lids(0.5)
            self._set_mouth((1.0 - math.cos(2 * math.pi * phase)) / 2)
        else:
            self._sleep_transition_started = None
            self.sleeping = True
            self._sleep_started = now
            self._set_mouth(0.0)
            self._set_lids(1.0)
            self.canvas.itemconfigure("nightcap", state=tk.NORMAL)
            self._animate_sleep(now)

    def _animate_sleep(self, now: float) -> None:
        for index, item in enumerate(self._sleep_zs):
            progress = (
                (now - self._sleep_started + index * SLEEP_Z_CYCLE_SECONDS / 3)
                % SLEEP_Z_CYCLE_SECONDS
            ) / SLEEP_Z_CYCLE_SECONDS
            self._coords(
                item,
                FACE_WIDTH / 2 + 13 + progress * 35,
                FACE_HEIGHT * 0.52 + 25 - progress * 39,
            )
            self.canvas.itemconfigure(item, state=tk.NORMAL)

    def _draw_leaf(
        self,
        base_x: float,
        base_y: float,
        angle_degrees: float,
        length: float,
        width: float,
        fill: str,
    ) -> None:
        angle = math.radians(angle_degrees)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        steps = 8
        side_a: list[tuple[float, float]] = []
        side_b: list[tuple[float, float]] = []
        for step in range(steps + 1):
            t = step / steps
            half = (
                width / 2 * math.sin(math.pi * t) * (1 + 0.25 * math.sin(6 * math.pi * t))
            )
            along = length * t
            side_a.append((along, half))
            side_b.append((along, -half))
        points: list[float] = []
        for along, across in side_a + side_b[::-1]:
            points.extend(
                (
                    base_x + along * cos_a - across * sin_a,
                    base_y + along * sin_a + across * cos_a,
                )
            )
        self.canvas.create_polygon(
            points, fill=fill, outline=self.background, smooth=True
        )
        self.canvas.create_line(
            base_x,
            base_y,
            base_x + length * 0.9 * cos_a,
            base_y + length * 0.9 * sin_a,
            fill=self.colors["green_selected"],
        )

    def _draw(self) -> None:
        canvas = self.canvas
        center_x, center_y = FACE_WIDTH / 2, FACE_HEIGHT * 0.52
        dark_green = self.colors["text"]
        green = self.colors["green"]
        light = self.colors["green_selected"]
        for angle in range(0, 360, 30):
            self._draw_leaf(center_x, center_y, angle - 90, 58, 26, dark_green)
        for angle in range(15, 375, 30):
            self._draw_leaf(center_x, center_y, angle - 90, 44, 22, green)
        self._draw_leaf(center_x, center_y - 20, -90, 52, 20, dark_green)
        for sign in (-1, 1):
            canvas.create_line(
                center_x + sign * 36, center_y - 30,
                center_x + sign * 50, center_y - 44,
                center_x + sign * 58, center_y - 40,
                smooth=True, fill=dark_green, width=2,
            )
        for sign in (-1, 1):
            self._draw_leaf(
                center_x + sign * 6, center_y + 26, 90 + sign * 55, 34, 14, green
            )
            self._draw_leaf(
                center_x + sign * 10, center_y + 12, 90 + sign * 80, 30, 12, dark_green
            )
        canvas.create_oval(
            center_x - 25, center_y - 33, center_x + 25, center_y + 35,
            fill=green, outline=dark_green,
        )
        self._nose_item = canvas.create_polygon(
            center_x, center_y - 6,
            center_x - 5, center_y + 14,
            center_x - 8, center_y + 16,
            center_x, center_y + 18,
            center_x + 8, center_y + 16,
            center_x + 5, center_y + 14,
            fill=dark_green, outline="", smooth=False,
        )
        for sign in (-1, 1):
            eye_x = center_x + sign * 11
            brow = canvas.create_line(
                eye_x - 9, center_y - 12,
                eye_x, center_y - 17,
                eye_x + 9, center_y - 12,
                smooth=True, fill=dark_green, width=3,
            )
            self._brows.append((brow, eye_x, center_y))
            self._eyes.append(
                canvas.create_oval(
                    eye_x - 7, center_y - 10, eye_x + 7, center_y - 3,
                    fill=light, outline=dark_green,
                )
            )
            pupil = canvas.create_oval(
                eye_x - 2.5, center_y - 9.5, eye_x + 2.5, center_y - 3.5,
                fill=dark_green, outline="",
            )
            self._pupils.append((pupil, eye_x, center_y - 6.5))
            lid = canvas.create_oval(
                0, 0, 0, 0, fill=green, outline=dark_green, state=tk.HIDDEN
            )
            self._lids.append((lid, eye_x, center_y - 10))
            self._draw_leaf(
                center_x + sign * 4, center_y + 24, 90 + sign * 90, 22, 9, dark_green
            )
        for sign in (-1, 1):
            eye_x = center_x + sign * 11
            canvas.create_oval(
                eye_x - 8.5, center_y - 11.5,
                eye_x + 8.5, center_y - 1.5,
                fill="", outline=GLASSES_COLOR, width=GLASSES_WIDTH,
                state=tk.HIDDEN, tags="reading_glasses",
            )
            canvas.create_line(
                eye_x + sign * 8.5, center_y - 7,
                eye_x + sign * 11, center_y - 8.5,
                fill=GLASSES_COLOR, width=GLASSES_WIDTH,
                state=tk.HIDDEN, tags="reading_glasses",
            )
        canvas.create_line(
            center_x - 2.5, center_y - 7,
            center_x, center_y - 8.5,
            center_x + 2.5, center_y - 7,
            fill=GLASSES_COLOR, width=GLASSES_WIDTH, smooth=True,
            state=tk.HIDDEN, tags="reading_glasses",
        )
        self._mouth_item = canvas.create_oval(
            0, 0, 0, 0, fill=dark_green, outline=light
        )
        self._set_mouth(0.0)
        canvas.create_polygon(
            39, 38, 42, 28, 48, 19, 57, 14, 68, 13,
            78, 16, 86, 22, 94, 24, 96, 29, 86, 29,
            77, 25, 83, 38,
            fill="#8cbd3c", outline="#28552e", width=1.5, smooth=True,
            state=tk.HIDDEN, tags="nightcap",
        )
        canvas.create_polygon(
            39, 36, 44, 34, 79, 34, 84, 36, 84, 40,
            79, 42, 44, 42, 39, 40,
            fill="#b9dd83", outline="#28552e", width=1.2, smooth=True,
            state=tk.HIDDEN, tags="nightcap",
        )
        for x, y, radius in (
            (96, 26, 5), (91, 24, 3.2), (92, 20, 3.2),
            (96, 19, 3.2), (100, 21, 3.2), (102, 25, 3.2),
            (101, 29, 3.2), (97, 32, 3.2), (93, 31, 3.2),
            (90, 28, 3.2),
        ):
            canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill="#d0ed9e", outline="", state=tk.HIDDEN,
                tags=("nightcap", "nightcap_pom"),
            )

    def _start_eye_animation(self) -> None:
        gaze = [0.0, 0.0]
        target = [0.0, 0.0]
        angle = [0.0]
        sweep_dir = [1]
        sweep_ticks = [WAITING_SWEEP_TICKS]
        ticks_until_shift = 20
        ticks_until_blink = random.randint(40, 100)
        ticks_until_twitch = random.randint(200, 400)
        blink_frame = len(BLINK_LID_LEVELS)

        def tick() -> None:
            nonlocal ticks_until_shift, ticks_until_blink, ticks_until_twitch, blink_frame
            if not self.animations_enabled:
                gaze[0] = gaze[1] = target[0] = target[1] = 0.0
                blink_frame = len(BLINK_LID_LEVELS)
                self._eye_after = self.root.after(EYE_FRAME_MS, tick)
                return
            now = time.monotonic()
            if (
                not self.sleeping
                and self._sleep_transition_started is None
                and not (self.loading or self.waiting or self.recording or self.speaking)
                and now - self._last_activity >= SLEEP_IDLE_SECONDS
            ):
                self._sleep_transition_started = now
                self._set_nose(0.0)
                self._nose_twitch_frame = len(NOSE_TWITCH_OFFSETS)
            if self._sleep_transition_started is not None:
                blink_frame = len(BLINK_LID_LEVELS) + 1
                self._animate_sleep_transition(now)
                self._eye_after = self.root.after(EYE_FRAME_MS, tick)
                return
            if self.sleeping:
                blink_frame = len(BLINK_LID_LEVELS) + 1
                self._animate_sleep(now)
                self._eye_after = self.root.after(EYE_FRAME_MS, tick)
                return
            ticks_until_shift -= 1
            ticks_until_twitch -= 1
            if (
                ticks_until_twitch <= 0
                and self._nose_twitch_frame >= len(NOSE_TWITCH_OFFSETS)
            ):
                self._nose_twitch_frame = 0
                ticks_until_twitch = random.randint(200, 400)
            if self._nose_twitch_frame < len(NOSE_TWITCH_OFFSETS):
                self._set_nose(NOSE_TWITCH_OFFSETS[self._nose_twitch_frame])
                self._nose_twitch_frame += 1
            if self.loading:
                blink_frame = len(BLINK_LID_LEVELS) + 1
            else:
                ticks_until_blink -= 1
                if ticks_until_blink <= 0 and blink_frame >= len(BLINK_LID_LEVELS):
                    blink_frame = 0
                    # Occasionally blink twice in quick succession.
                    ticks_until_blink = (
                        random.randint(5, 8)
                        if random.random() < 0.2
                        else random.randint(60, 160)
                    )
                if blink_frame < len(BLINK_LID_LEVELS):
                    self._set_lids(BLINK_LID_LEVELS[blink_frame])
                    blink_frame += 1
                elif blink_frame == len(BLINK_LID_LEVELS):
                    self._set_lids(0.0)
                    blink_frame += 1
            if self.loading:
                angle[0] += LOADING_RADIANS_PER_TICK
                target[0] = LOADING_RADIUS * math.cos(angle[0])
                target[1] = LOADING_RADIUS * math.sin(angle[0])
                ticks_until_shift = 20
            elif self.waiting:
                sweep_ticks[0] -= 1
                if sweep_ticks[0] <= 0:
                    sweep_dir[0] = -sweep_dir[0]
                    sweep_ticks[0] = WAITING_SWEEP_TICKS
                target[0] = sweep_dir[0] * WAITING_SWEEP
                target[1] = 0.0
                ticks_until_shift = 20
            elif self.speaking:
                target[0] = target[1] = 0.0
                ticks_until_shift = 20
            elif ticks_until_shift <= 0:
                target[0] = random.uniform(-3.5, 3.5)
                target[1] = random.uniform(-1.5, 1.5)
                ticks_until_shift = random.randint(25, 90)
            for axis in (0, 1):
                gaze[axis] += (target[axis] - gaze[axis]) * 0.35
            for pupil, eye_x, eye_y in self._pupils:
                x, y = eye_x + gaze[0], eye_y + gaze[1]
                self._coords(pupil, x - 2.5, y - 3, x + 2.5, y + 3)
            self._eye_after = self.root.after(EYE_FRAME_MS, tick)

        tick()

    def _coords(self, item: int, *points: float) -> None:
        """Move an item using unscaled design coordinates."""
        self.canvas.coords(item, *(point * FACE_SCALE for point in points))

    def _set_lids(self, closed: float) -> None:
        """Draw the eyelids over the eyes; 0 is open and 1 is fully closed."""
        for lid, eye_x, eye_top in self._lids:
            if closed <= 0:
                self.canvas.itemconfigure(lid, state=tk.HIDDEN)
                continue
            self._coords(
                lid,
                eye_x - 7, eye_top,
                eye_x + 7, eye_top + EYE_HEIGHT * closed,
            )
            self.canvas.itemconfigure(lid, state=tk.NORMAL)

    def _set_nose(self, offset: float) -> None:
        cx, cy = FACE_WIDTH / 2, FACE_HEIGHT * 0.52
        self._coords(
            self._nose_item,
            cx, cy - 6,
            cx - 5 + offset, cy + 14,
            cx - 8 + offset, cy + 16,
            cx + offset, cy + 18,
            cx + 8 + offset, cy + 16,
            cx + 5 + offset, cy + 14,
        )

    def _set_mouth(self, level: float) -> None:
        self.mouth_level = level
        cx, cy = FACE_WIDTH / 2, FACE_HEIGHT * 0.52 + 25
        half_width = 13 + 9 * level
        half_height = 2 + 15 * level
        self._coords(
            self._mouth_item,
            cx - half_width,
            cy - half_height,
            cx + half_width,
            cy + half_height,
        )

    def _set_brows(self, lifts: tuple[float, float]) -> None:
        """Raise each brow by 0-1 (left, right) and arch it as it lifts."""
        for (brow, eye_x, eye_y), lift in zip(self._brows, lifts):
            rise = 7 * lift
            self._coords(
                brow,
                eye_x - 9, eye_y - 12 - rise * 0.6,
                eye_x, eye_y - 17 - rise,
                eye_x + 9, eye_y - 12 - rise * 0.8,
            )
