import base64
import json
import tempfile
import unittest
from pathlib import Path

from dataset_recorder import DatasetRecorder
import export_dataset


class ExportDatasetTests(unittest.TestCase):
    def _create_sample_dataset(self, root: Path) -> Path:
        recorder = DatasetRecorder(root)
        fake_png = b"\x89PNG\r\n\x1a\n" + b"sample-chess-frame"
        encoded = base64.b64encode(fake_png).decode("ascii")

        recorder.record(
            source="chess_study",
            model="qwen3-vl:8b-instruct",
            prompt="Play Black.",
            tool_name="move_piece",
            tool_arguments={"observation": "Opening move", "from_square": "e7", "to_square": "e5"},
            screenshot_b64=encoded,
            screenshot_size=(1024, 1024),
        )
        recorder.record(
            source="Desktop control",
            model="qwen3-vl:4b-instruct",
            prompt="Open Firefox",
            tool_name="launch_application",
            tool_arguments={"title_or_app": "Firefox"},
            screenshot_b64=None,
        )
        return recorder.jsonl_path

    def test_export_openai_and_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl_path = self._create_sample_dataset(root)
            out_path = root / "openai_out.jsonl"

            rc = export_dataset.main([
                "export",
                "-i", str(jsonl_path),
                "-o", str(out_path),
                "-f", "openai",
                "--source", "chess_study",
                "--require-image",
            ])
            self.assertEqual(rc, 0)
            lines = out_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            item = json.loads(lines[0])
            self.assertEqual(item["messages"][0]["role"], "system")
            self.assertEqual(item["messages"][1]["content"][0]["type"], "image_url")
            tool_call = item["messages"][2]["tool_calls"][0]["function"]
            self.assertEqual(tool_call["name"], "move_piece")
            self.assertEqual(json.loads(tool_call["arguments"])["from_square"], "e7")

    def test_export_sharegpt_and_val_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jsonl_path = self._create_sample_dataset(root)
            out_path = root / "sharegpt.jsonl"

            rc = export_dataset.main([
                "export",
                "-i", str(jsonl_path),
                "-o", str(out_path),
                "-f", "sharegpt",
                "--val-split", "0.5",
            ])
            self.assertEqual(rc, 0)
            train_path = root / "sharegpt_train.jsonl"
            val_path = root / "sharegpt_val.jsonl"
            self.assertTrue(train_path.is_file())
            self.assertTrue(val_path.is_file())
            self.assertEqual(
                len(train_path.read_text(encoding="utf-8").splitlines())
                + len(val_path.read_text(encoding="utf-8").splitlines()),
                2,
            )

    def test_compare_tool_calls_ignores_observation(self) -> None:
        name_ok, exact_ok = export_dataset._compare_tool_calls(
            "move_piece",
            {"observation": "A", "from_square": "e7", "to_square": "e5"},
            "move_piece",
            {"observation": "Different wording", "from_square": "e7", "to_square": "e5"},
        )
        self.assertTrue(name_ok)
        self.assertTrue(exact_ok)


if __name__ == "__main__":
    unittest.main()
