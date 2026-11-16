import os
import runpy
import unittest
from collections import defaultdict
from unittest.mock import Mock, patch

from PIL import ImageDraw

try:
    import pygame
except ImportError:
    pygame = None


@unittest.skipIf(pygame is None, "Pong requires pygame")
class PongTests(unittest.TestCase):
    def setUp(self) -> None:
        random_patch = patch("random.randint", return_value=300)
        random_patch.start()
        self.addCleanup(random_patch.stop)

    def test_tail_points_behind_ball_and_follows_wall_bounce(self) -> None:
        start = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
        space = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
        frames = 110
        events = [[]] + [[start]] + [[] for _ in range(frames - 1)] + [
            [space], [], [pygame.event.Event(pygame.QUIT)]
        ]
        lines, positions = [], []
        with patch("random.randint", return_value=300), \
             patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}), \
             patch.object(pygame.event, "get", side_effect=events), \
             patch.object(pygame.key, "get_pressed", return_value=defaultdict(bool)), \
             patch.object(pygame.time, "Clock", return_value=Mock()), \
             patch.object(pygame.draw, "line", side_effect=lambda *args: lines.append(args)), \
             patch.object(pygame.draw, "circle", side_effect=lambda *args: positions.append(args[2])):
            with self.assertRaises(SystemExit):
                runpy.run_path("pong.py", run_name="__main__")

        self.assertEqual(len(lines), frames + 2)
        start_point, end_point = lines[0][2], lines[0][3]
        self.assertLess(end_point[0], start_point[0])
        self.assertLess(end_point[1], start_point[1])
        bounce_index = next(i for i, point in enumerate(positions) if point[1] == 590)
        bounce_line = lines[bounce_index - 1]
        self.assertLess(bounce_line[3][0], bounce_line[2][0])
        self.assertGreater(bounce_line[3][1], bounce_line[2][1])
        self.assertEqual(lines[-1][2:4], lines[-2][2:4])

    def test_random_vertical_launches_at_start_after_points_and_restart(self) -> None:
        start = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
        positions = []
        state = {"frame": 0, "ended_at": None}
        original_text = ImageDraw.ImageDraw.text

        def events():
            state["frame"] += 1
            if state["frame"] == 2:
                return [start]
            if state["ended_at"] is not None and state["frame"] == state["ended_at"] + 2:
                return [start]
            if state["ended_at"] is not None and state["frame"] == state["ended_at"] + 4:
                return [pygame.event.Event(pygame.QUIT)]
            if state["frame"] > 6000:
                return [pygame.event.Event(pygame.QUIT)]
            return []

        def render(draw, xy, text, *args, **kwargs):
            if "wins!" in text and state["ended_at"] is None:
                state["ended_at"] = state["frame"]
            return original_text(draw, xy, text, *args, **kwargs)

        with patch("random.randint", side_effect=[100] + [120] * 10 + [200]) as randint, \
             patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}), \
             patch.object(pygame.event, "get", side_effect=events), \
             patch.object(pygame.key, "get_pressed", return_value=defaultdict(bool)), \
             patch.object(pygame.time, "Clock", return_value=Mock()), \
             patch.object(pygame.draw, "circle", side_effect=lambda *args: positions.append(args[2])), \
             patch.object(ImageDraw.ImageDraw, "text", autospec=True, side_effect=render):
            with self.assertRaises(SystemExit):
                runpy.run_path("pong.py", run_name="__main__")

        self.assertIsNotNone(state["ended_at"])
        self.assertEqual(positions[0], (400, 100))
        self.assertEqual(positions[1], (403, 103))
        self.assertEqual(positions.count((400, 120)), 10)
        self.assertIn((403, 203), positions)
        self.assertEqual(randint.call_count, 12)
        self.assertTrue(all(call.args == (10, 590) for call in randint.call_args_list))

    def test_space_pauses_and_resumes_ball_and_paddles(self) -> None:
        space = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
        events = [[space], [], [space], [], [], [space], [], [pygame.event.Event(pygame.QUIT)]]
        circles, rectangles, texts = [], [], []
        original_text = ImageDraw.ImageDraw.text

        def capture_text(draw, xy, text, *args, **kwargs):
            texts.append(text)
            return original_text(draw, xy, text, *args, **kwargs)

        with patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}), \
             patch.object(pygame.event, "get", side_effect=events), \
             patch.object(pygame.key, "get_pressed", return_value=defaultdict(bool, {pygame.K_w: True})), \
             patch.object(pygame.time, "Clock", return_value=Mock()), \
             patch.object(pygame.draw, "circle", side_effect=lambda *args: circles.append(args[2])), \
             patch.object(pygame.draw, "rect", side_effect=lambda *args: rectangles.append(args[2])), \
             patch.object(ImageDraw.ImageDraw, "text", autospec=True, side_effect=capture_text):
            with self.assertRaises(SystemExit):
                runpy.run_path("pong.py", run_name="__main__")

        self.assertEqual(circles[1:5], [(406, 306)] * 4)
        self.assertEqual(circles[5:], [(409, 309), (412, 312)])
        self.assertEqual([rectangles[i * 2][1] for i in range(1, 5)], [230] * 4)
        self.assertEqual(rectangles[10][1], 220)
        self.assertEqual(texts.count("Paused - Press Space to resume"), 3)

    def test_selectable_speed_scales_ball_and_paddle_movement(self) -> None:
        for keys, multiplier in (
            ((pygame.K_LEFT, pygame.K_LEFT), 0.1),
            ((pygame.K_LEFT,), 0.5),
            ((), 1.0),
            ((pygame.K_RIGHT,), 1.5),
        ):
            with self.subTest(multiplier=multiplier):
                initial_events = [
                    pygame.event.Event(pygame.KEYDOWN, key=key) for key in keys
                ]
                events = [
                    initial_events,
                    [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)],
                    [], [], [],
                    [pygame.event.Event(pygame.QUIT)],
                ]
                circles = []
                rectangles = []
                with patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}), \
                     patch.object(pygame.event, "get", side_effect=events), \
                     patch.object(pygame.key, "get_pressed", return_value=defaultdict(bool, {pygame.K_w: True})), \
                     patch.object(pygame.time, "Clock", return_value=Mock()), \
                     patch.object(pygame.draw, "circle", side_effect=lambda *args: circles.append(args)), \
                     patch.object(pygame.draw, "rect", side_effect=lambda *args: rectangles.append(args)):
                    with self.assertRaises(SystemExit):
                        runpy.run_path("pong.py", run_name="__main__")
                self.assertEqual(circles[0][2], (400, 300))
                self.assertEqual(circles[-1][2], (round(400 + 12 * multiplier), round(300 + 12 * multiplier)))
                self.assertEqual(rectangles[-2][2][1], round(250 - 40 * multiplier))

    def test_escape_exits_and_closes_display(self) -> None:
        escape = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        start = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
        for event_batches in ([[], [escape]], [[start], [escape]], [[start], [start], [escape]]):
            with self.subTest(event_batches=event_batches), \
                 patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}), \
                 patch.object(pygame.event, "get", side_effect=event_batches), \
                 patch.object(pygame.key, "get_pressed", return_value=defaultdict(bool)), \
                 patch.object(pygame.time, "Clock", return_value=Mock()):
                with self.assertRaises(SystemExit) as exit_error:
                    runpy.run_path("pong.py", run_name="__main__")
                self.assertIsNone(exit_error.exception.code)
                self.assertFalse(pygame.display.get_init())

    def run_game(self, frames: int, keys: dict[int, bool]) -> tuple[list, list]:
        events = [[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)]]
        events += [[] for _ in range(frames - 1)] + [[pygame.event.Event(pygame.QUIT)]]
        circles = []
        rectangles = []
        clock = Mock()
        with patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}), \
             patch.object(pygame.event, "get", side_effect=events), \
             patch.object(pygame.key, "get_pressed", return_value=defaultdict(bool, keys)), \
             patch.object(pygame.time, "Clock", return_value=clock), \
             patch.object(pygame.draw, "circle", side_effect=lambda *args: circles.append(args)), \
             patch.object(pygame.draw, "rect", side_effect=lambda *args: rectangles.append(args)):
            with self.assertRaises(SystemExit) as exit_error:
                runpy.run_path("pong.py", run_name="__main__")
        self.assertIsNone(exit_error.exception.code)
        return circles, rectangles

    def test_paddles_move_and_ball_bounces_off_right_paddle(self) -> None:
        circles, rectangles = self.run_game(150, {pygame.K_w: True, pygame.K_k: True})
        self.assertEqual(rectangles[-2][2][1], 0)
        self.assertEqual(rectangles[-1][2][1], 500)
        positions = [args[2] for args in circles]
        self.assertTrue(any(
            positions[i][0] >= 780 and positions[i + 1][0] < positions[i][0]
            for i in range(len(positions) - 1)
        ))
        self.assertTrue(any(
            positions[i][1] == 590 and positions[i + 1][1] < positions[i][1]
            for i in range(len(positions) - 1)
        ))
        self.assertTrue(all(10 <= position[1] <= 590 for position in positions))

    def test_right_paddle_moves_up_with_i_and_down_with_k(self) -> None:
        for key, expected_y in ((pygame.K_i, 240), (pygame.K_k, 260)):
            with self.subTest(key=key):
                _, rectangles = self.run_game(1, {key: True})
                self.assertEqual(rectangles[-1][2][1], expected_y)

    def test_missed_ball_returns_to_center(self) -> None:
        circles, _ = self.run_game(150, {})
        self.assertIn((400, 300), [args[2] for args in circles])

    def test_match_waits_for_space_scores_eleven_balls_and_restarts(self) -> None:
        start = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
        quit_event = pygame.event.Event(pygame.QUIT)
        texts = []
        positions = []
        state = {"frame": 0, "ended_at": None, "scores_at_end": None}

        def events():
            frame = state["frame"]
            state["frame"] += 1
            if frame == 3:
                return [start]
            if state["ended_at"] is not None and frame == state["ended_at"] + 4:
                return [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT)]
            if state["ended_at"] is not None and frame == state["ended_at"] + 5:
                return [start]
            if state["ended_at"] is not None and frame == state["ended_at"] + 8:
                return [quit_event]
            if frame > 5000:
                return [quit_event]
            return []

        def draw_circle(_screen, _color, position, _radius):
            positions.append(position)

        original_text = ImageDraw.ImageDraw.text

        def render(draw, xy, text, *args, **kwargs):
            texts.append(text)
            if "wins!" in text and state["ended_at"] is None:
                state["ended_at"] = state["frame"]
                state["scores_at_end"] = next(
                    item for item in reversed(texts) if " : " in item
                )
            return original_text(draw, xy, text, *args, **kwargs)

        with patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}), \
             patch.object(pygame.event, "get", side_effect=events), \
             patch.object(pygame.key, "get_pressed", return_value=defaultdict(bool)), \
             patch.object(pygame.time, "Clock", return_value=Mock()), \
             patch.object(ImageDraw.ImageDraw, "text", autospec=True, side_effect=render), \
             patch.object(pygame.draw, "circle", side_effect=draw_circle):
            with self.assertRaises(SystemExit):
                runpy.run_path("pong.py", run_name="__main__")

        self.assertEqual(positions[:3], [(400, 300)] * 3)
        self.assertEqual(positions[3], (403, 303))
        self.assertIn("Press Space to start", texts)
        self.assertIsNotNone(state["ended_at"])
        left, right = map(int, state["scores_at_end"].split(" : "))
        self.assertEqual(left + right, 11)
        self.assertGreater(left, 0)
        self.assertGreater(right, 0)
        expected = "Left player" if left > right else "Right player"
        self.assertIn(f"{expected} wins! Press Space to play again", texts)
        end_index = texts.index(f"{expected} wins! Press Space to play again")
        self.assertIn("0 : 0", texts[end_index + 1:])
        self.assertIn("Balls remaining: 11", texts[end_index + 1:])
        self.assertIn("Speed: 1.5x (Left/Right to change)", texts[end_index + 1:])


if __name__ == "__main__":
    unittest.main()
