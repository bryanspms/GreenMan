import tkinter as tk
import unittest

from face import GreenManFace

COLORS = {
    "background": "#e8f1e8",
    "text": "#183b24",
    "green": "#2f6b3f",
    "green_selected": "#c8dfca",
}


class GreenManFaceTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.face = GreenManFace(self.root, self.root, COLORS, COLORS["background"])

    def tearDown(self) -> None:
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

    def test_pupils_center_while_speaking(self) -> None:
        self.face.start_speaking(None)
        for _ in range(40):
            self.root.update()
            self.root.after(40)
        pupil, eye_x, eye_y = self.face._pupils[0]
        x1, y1, x2, y2 = self.face.canvas.coords(pupil)
        self.assertAlmostEqual((x1 + x2) / 2, eye_x, delta=0.5)
        self.assertAlmostEqual((y1 + y2) / 2, eye_y, delta=0.5)
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
