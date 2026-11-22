import base64
import json
import tempfile
import unittest
from pathlib import Path

from dataset_recorder import DatasetRecorder


class DatasetRecorderTests(unittest.TestCase):
    def test_records_jsonl_and_saves_image(self) -> None:
        fake_png = b"\x89PNG\r\n\x1a\n" + b"test-image-bytes"
        encoded = base64.b64encode(fake_png).decode("ascii")

        with tempfile.TemporaryDirectory() as tmp:
            recorder = DatasetRecorder(Path(tmp))
            jsonl_path = recorder.record(
                source="chess_study",
                model="qwen3-vl:8b-instruct",
                prompt="Play Black.",
                tool_name="move_piece",
                tool_arguments={"from_square": "e7", "to_square": "e5"},
                screenshot_b64=encoded,
                screenshot_size=(1024, 1024),
            )

            lines = jsonl_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry["source"], "chess_study")
            self.assertEqual(entry["tool_call"]["name"], "move_piece")
            self.assertEqual(entry["tool_call"]["arguments"]["from_square"], "e7")
            self.assertTrue(entry["screenshot"].startswith("images/"))
            self.assertTrue(entry["screenshot"].endswith(".png"))
            self.assertEqual((Path(tmp) / entry["screenshot"]).read_bytes(), fake_png)


if __name__ == "__main__":
    unittest.main()
