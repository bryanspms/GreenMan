import json
import base64
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from app import (
    DEFAULT_MODEL,
    IMAGE_CONTEXT_TOKENS,
    IMAGE_RESPONSE_TOKENS,
    MAX_IMAGE_BYTES,
    MODEL_OPTIONS,
    DesktopAgent,
    TOOL_MODES,
    calculate_cpu_utilization,
    format_elapsed_time,
    is_valid_workspace,
    is_text_tool_call,
    load_dropped_image,
    load_ollama_model,
    local_ollama_url,
    load_user_preferences,
    ollama_http_error_message,
    save_user_preferences,
    read_cpu_counters,
    read_system_status,
    resolve_workspace_path,
    tools_for_mode,
)


class WorkspacePathTests(unittest.TestCase):
    def test_workspace_is_valid_only_while_it_is_a_directory(self) -> None:
        with TemporaryDirectory() as folder:
            self.assertTrue(is_valid_workspace(Path(folder)))
            self.assertFalse(is_valid_workspace(Path(folder) / "missing"))
        self.assertFalse(is_valid_workspace(None))

    def test_preferences_restore_valid_workspace_and_assistant_mode(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            workspace = root / "workspace"
            workspace.mkdir()
            preferences_file = root / "config" / "preferences.json"

            self.assertIsNone(
                save_user_preferences(preferences_file, workspace, "Workspace files")
            )

            (
                restored_workspace,
                restored_mode,
                restored_model,
                error,
            ) = load_user_preferences(preferences_file)

        self.assertEqual(restored_workspace, workspace)
        self.assertEqual(restored_mode, "Workspace files")
        self.assertEqual(restored_model, DEFAULT_MODEL)
        self.assertIsNone(error)

    def test_preferences_ignore_a_workspace_that_no_longer_exists(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            preferences_file = root / "preferences.json"
            preferences_file.write_text(
                json.dumps(
                    {
                        "workspace": str(root / "removed"),
                        "assistant_mode": "Screenshot",
                    }
                ),
                encoding="utf-8",
            )

            workspace, mode, model, error = load_user_preferences(preferences_file)

        self.assertIsNone(workspace)
        self.assertEqual(mode, "Screenshot")
        self.assertEqual(model, DEFAULT_MODEL)
        self.assertIsNone(error)

    def test_preferences_default_to_questions_for_unknown_mode(self) -> None:
        with TemporaryDirectory() as folder:
            preferences_file = Path(folder) / "preferences.json"
            preferences_file.write_text(
                json.dumps({"workspace": None, "assistant_mode": "Unknown"}),
                encoding="utf-8",
            )

            workspace, mode, model, error = load_user_preferences(preferences_file)

        self.assertIsNone(workspace)
        self.assertEqual(mode, "Questions only")
        self.assertEqual(model, DEFAULT_MODEL)
        self.assertIsNone(error)

    def test_preferences_restore_selected_model(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            workspace = root / "workspace"
            workspace.mkdir()
            preferences_file = root / "preferences.json"

            self.assertIsNone(
                save_user_preferences(
                    preferences_file, workspace, "Screenshot", "qwen3-vl:8b"
                )
            )

            restored_workspace, mode, model, error = load_user_preferences(
                preferences_file
            )

        self.assertEqual(restored_workspace, workspace)
        self.assertEqual(mode, "Screenshot")
        self.assertEqual(model, "qwen3-vl:8b")
        self.assertIsNone(error)

    def test_resolves_path_inside_workspace(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertEqual(resolve_workspace_path(root, "notes.txt"), root / "notes.txt")

    def test_rejects_parent_traversal(self) -> None:
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                resolve_workspace_path(Path(folder), "../outside.txt")

    def test_rejects_absolute_path_outside_workspace(self) -> None:
        with TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                resolve_workspace_path(Path(folder), "/etc/passwd")

    def test_rejects_symlink_escape(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder) / "workspace"
            outside = Path(folder) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "shortcut").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                resolve_workspace_path(root, "shortcut/file.txt")


class SystemStatusTests(unittest.TestCase):
    def test_reads_aggregate_cpu_counters(self) -> None:
        with TemporaryDirectory() as folder:
            stat_path = Path(folder) / "stat"
            stat_path.write_text("cpu 100 20 30 800 50 0 0 0 0 0\n", encoding="utf-8")

            self.assertEqual(read_cpu_counters(stat_path), (1000, 850))

    def test_calculates_cpu_utilization_between_samples(self) -> None:
        self.assertEqual(calculate_cpu_utilization((1000, 800), (1200, 900)), 50)
        self.assertIsNone(calculate_cpu_utilization(None, (1200, 900)))

    def test_formats_elapsed_time_in_seconds_and_minutes(self) -> None:
        self.assertEqual(format_elapsed_time(12.34), "12.3 seconds")
        self.assertEqual(format_elapsed_time(125.6), "2 min 5.6 sec")

    def test_reads_cpu_temperature_and_gpu_utilization_from_sysfs(self) -> None:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            cpu_sensor = root / "class/hwmon/hwmon0"
            gpu_device = root / "class/drm/card0/device"
            cpu_sensor.mkdir(parents=True)
            gpu_device.mkdir(parents=True)
            (cpu_sensor / "name").write_text("coretemp", encoding="utf-8")
            (cpu_sensor / "temp1_input").write_text("55250", encoding="utf-8")
            (cpu_sensor / "temp1_label").write_text("Package id 0", encoding="utf-8")
            (gpu_device / "gpu_busy_percent").write_text("60", encoding="utf-8")

            with patch("app.shutil.which", return_value=None):
                self.assertEqual(read_system_status(root), (55, 60))

    def test_reads_nvidia_gpu_utilization(self) -> None:
        with TemporaryDirectory() as folder:
            with patch("app.shutil.which", return_value="/usr/bin/nvidia-smi"):
                with patch(
                    "app.subprocess.run",
                    return_value=Mock(stdout="56\n"),
                ) as run:
                    self.assertEqual(
                        read_system_status(Path(folder)), (None, 56)
                    )

        self.assertEqual(
            run.call_args.args[0],
            [
                "/usr/bin/nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
        )

    def test_missing_sensors_are_reported_as_unavailable(self) -> None:
        with TemporaryDirectory() as folder:
            with patch("app.shutil.which", return_value=None):
                self.assertEqual(read_system_status(Path(folder)), (None, None))

    def test_loads_supported_dropped_image_as_base64(self) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\nsample-image"
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "screenshot.png"
            image_path.write_bytes(image_bytes)

            name, encoded = load_dropped_image(image_path)

        self.assertEqual(name, "screenshot.png")
        self.assertEqual(encoded, base64.b64encode(image_bytes).decode("ascii"))

    def test_rejects_unsupported_dropped_file(self) -> None:
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "notes.txt"
            image_path.write_text("not an image", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Image must use"):
                load_dropped_image(image_path)

    def test_rejects_dropped_image_over_size_limit(self) -> None:
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "large.png"
            image_path.write_bytes(b"x" * (MAX_IMAGE_BYTES + 1))

            with self.assertRaisesRegex(ValueError, "10 MB image limit"):
                load_dropped_image(image_path)


class OllamaUrlTests(unittest.TestCase):
    def test_accepts_local_http_urls(self) -> None:
        self.assertEqual(local_ollama_url("http://localhost:11434/"), "http://localhost:11434")
        self.assertEqual(local_ollama_url("http://127.0.0.1:11434"), "http://127.0.0.1:11434")

    def test_rejects_non_local_urls(self) -> None:
        for url in ("https://localhost:11434", "http://example.com", "http://192.168.1.5:11434"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_ollama_url(url)


class ToolCallResponseTests(unittest.TestCase):
    def test_model_selector_options_and_default(self) -> None:
        self.assertEqual(MODEL_OPTIONS, ("llama3.1:8b", "qwen3-vl:8b"))
        self.assertEqual(DEFAULT_MODEL, "llama3.1:8b")

    def test_model_load_request_uses_ollama_generate_load_api(self) -> None:
        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"model":"qwen3-vl:8b","done":true,"done_reason":"load"}'
            )

            load_ollama_model("http://127.0.0.1:11434", "qwen3-vl:8b")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/generate")
        self.assertEqual(payload["model"], "qwen3-vl:8b")
        self.assertEqual(payload["prompt"], "")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["keep_alive"], "5m")

    def test_model_load_failure_is_reported(self) -> None:
        with (
            patch(
                "app.urlopen",
                side_effect=URLError("Connection refused"),
            ),
            self.assertRaisesRegex(RuntimeError, "Could not load qwen3-vl:8b"),
        ):
            load_ollama_model(
                "http://127.0.0.1:11434", "qwen3-vl:8b"
            )

    def test_modes_expose_only_their_tools(self) -> None:
        expected = {
            "Questions only": set(),
            "Screenshot": {"take_screenshot"},
            "Desktop control": {"take_screenshot", "click", "type_text"},
            "Workspace files": {
                "list_files",
                "read_file",
                "view_image",
                "write_file",
            },
            "Run command": {"run_command"},
        }
        self.assertEqual(set(TOOL_MODES), set(expected))
        for mode, names in expected.items():
            with self.subTest(mode=mode):
                self.assertEqual(
                    {tool["function"]["name"] for tool in tools_for_mode(mode)},
                    names,
                )

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown assistant mode"):
            tools_for_mode("Everything")

    def test_chat_request_includes_only_selected_tools(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [{"role": "user", "content": "Take a screenshot."}]

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"content":"Done."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "llama3.1:8b",
                tools=tools_for_mode("Screenshot"),
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(
            [tool["function"]["name"] for tool in payload["tools"]],
            ["take_screenshot"],
        )

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"content":"Hello."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "llama3.1:8b",
                tools=tools_for_mode("Questions only"),
            )

        question_request = urlopen.call_args.args[0]
        self.assertNotIn("tools", json.loads(question_request.data))

    def test_qwen_image_request_uses_larger_context_and_disables_thinking(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {
                "role": "user",
                "content": "Describe this image.",
                "images": ["aGVsbG8="],
            }
        ]

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"role":"assistant","content":"A test image."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "qwen3-vl:8b",
                tools=[],
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertFalse(payload["think"])
        self.assertEqual(
            payload["options"],
            {
                "num_ctx": IMAGE_CONTEXT_TOKENS,
                "num_predict": IMAGE_RESPONSE_TOKENS,
            },
        )

    def test_non_qwen_image_request_does_not_get_qwen_options(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "user", "content": "Describe this image.", "images": ["aGVsbG8="]}
        ]

        with patch("app.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = (
                b'{"message":{"role":"assistant","content":"A test image."}}'
            )
            agent._chat(
                "http://localhost:11434/api/chat",
                "llama3.1:8b",
                tools=[],
            )

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertNotIn("think", payload)
        self.assertNotIn("options", payload)

    def test_chat_connection_error_includes_underlying_reason(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [{"role": "user", "content": "Hello."}]
        with (
            patch("app.urlopen", side_effect=URLError("Connection refused")),
            self.assertRaisesRegex(RuntimeError, "Connection refused"),
        ):
            agent._chat(
                "http://127.0.0.1:11434/api/chat",
                "llama3.1:8b",
                tools=[],
            )

    def test_chat_http_error_is_reported_as_http_error(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [{"role": "user", "content": "Hello."}]
        error = HTTPError(
            "http://127.0.0.1:11434/api/chat",
            500,
            "Internal Server Error",
            {},
            None,
        )
        error.read = Mock(return_value=b"model runner failed")
        with (
            patch("app.urlopen", side_effect=error),
            self.assertRaisesRegex(
                RuntimeError, "(?s)HTTP 500.*model runner failed"
            ),
        ):
            agent._chat(
                "http://127.0.0.1:11434/api/chat",
                "llama3.1:8b",
                tools=[],
            )

    def test_multimodal_http_error_explains_vision_model_requirement(self) -> None:
        error_body = json.dumps(
            {
                "error": json.dumps(
                    {
                        "error": {
                            "code": 400,
                            "message": (
                                "Multimodal data provided, but model does not support "
                                "multimodal requests."
                            ),
                            "type": "invalid_request_error",
                        }
                    }
                )
            }
        )

        message = ollama_http_error_message(
            "http://127.0.0.1:11434/api/chat", 400, error_body
        )

        self.assertIn("selected model does not support images", message)
        self.assertIn("vision and tool calling", message)

    def test_other_http_errors_keep_server_details(self) -> None:
        message = ollama_http_error_message(
            "http://127.0.0.1:11434/api/chat", 500, '{"error":"server failure"}'
        )
        self.assertIn("HTTP 500", message)
        self.assertIn("server failure", message)

    def test_detects_tool_request_returned_as_text(self) -> None:
        response = '{"name":"screenshot","parameters":{"filename":"screenshot.png"}}'
        self.assertTrue(is_text_tool_call(response))

    def test_does_not_match_regular_json_or_text(self) -> None:
        self.assertFalse(is_text_tool_call('{"name":"Ada"}'))
        self.assertFalse(is_text_tool_call("Hello, how can I help?"))

    def test_retries_plain_text_tool_request_without_tools(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "What is your name?"},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            side_effect=[
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"name":"screenshot","parameters":{"filename":"screenshot.png"}}',
                    }
                },
                {"message": {"role": "assistant", "content": "I am a local assistant."}},
            ]
        )

        agent._run_turn("http://localhost:11434", "llama3.1:8b")

        self.assertEqual(completed, [("I am a local assistant.", None)])
        self.assertEqual(agent._chat.call_args.kwargs["tools"], [])
        self.assertEqual(agent._chat.call_args_list[0].kwargs["tools"], [])
        self.assertEqual(agent.messages[-1]["content"], "I am a local assistant.")

    def test_empty_length_limited_response_is_reported_clearly(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Describe this image."},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            return_value={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "thinking": "Still reasoning",
                },
                "done_reason": "length",
            }
        )

        agent._run_turn("http://localhost:11434", "qwen3-vl:8b", "Workspace files")

        self.assertEqual(completed[0][0], "")
        self.assertIn("generation limit", completed[0][1])

    def test_rejects_tool_calls_outside_selected_mode(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Write a file."},
        ]
        agent.root = Mock()
        agent.root.after.side_effect = lambda _delay, callback, *args: callback(*args)
        completed = []
        agent._finish = lambda answer, error: completed.append((answer, error))
        agent._chat = Mock(
            return_value={
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "write_file",
                                "arguments": {"path": "HelloWorld.txt", "content": "Hello"},
                            }
                        }
                    ],
                }
            }
        )
        agent._execute_tool = Mock()

        agent._run_turn("http://localhost:11434", "llama3.1:8b", "Questions only")

        self.assertIn("not available in Questions only mode", completed[0][1])
        agent._execute_tool.assert_not_called()


class DesktopSafetyTests(unittest.TestCase):
    def test_finish_appends_elapsed_duration_after_answer(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.turn_started_at = 10.0
        agent.busy = True
        agent.working_status_after = None
        agent.root = Mock()
        agent.model_selector = Mock()
        agent.send_button = Mock()
        agent.new_chat_button = Mock()
        agent.mode_buttons = []
        agent.prompt = Mock()
        agent.url_entry = Mock()
        agent.workspace_button = Mock()
        agent.status = Mock()
        agent._append = Mock()
        agent._update_send_button = Mock()

        with patch("app.time.monotonic", return_value=13.25):
            agent._finish("Here is the answer.", None)

        self.assertEqual(
            agent._append.call_args_list,
            [
                unittest.mock.call("Assistant", "Here is the answer."),
                unittest.mock.call("Query Duration", "3.2 seconds"),
            ],
        )
        self.assertIsNone(agent.turn_started_at)
        self.assertFalse(agent.busy)
        agent.prompt.config.assert_called_once_with(state="normal")
        agent.url_entry.config.assert_called_once_with(state="normal")
        agent.workspace_button.config.assert_called_once_with(state="normal")

    def test_send_attaches_dropped_image_to_user_message(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.workspace = Path(".")
        agent.prompt = Mock()
        agent.prompt.get.return_value = "What does this error mean?"
        agent.prompt.delete = Mock()
        agent.pending_image = ("error.png", "aGVsbG8=")
        agent.messages = []
        agent.screen_observed = False
        agent.send_button = Mock()
        agent.new_chat_button = Mock()
        agent.model_selector = Mock()
        agent.url_entry = Mock()
        agent.workspace_button = Mock()
        agent.mode_buttons = []
        agent.status = Mock()
        agent.url_entry = Mock()
        agent.url_entry.get.return_value = "http://127.0.0.1:11434"
        agent.active_model = "qwen3-vl:8b"
        agent.tool_mode = Mock()
        agent.tool_mode.get.return_value = "Questions only"
        agent._append = Mock()
        agent._clear_pending_image = Mock()
        agent._update_working_status = Mock()

        with patch("app.threading.Thread") as thread:
            agent._send()

        self.assertEqual(
            agent.messages,
            [
                {
                    "role": "user",
                    "content": "What does this error mean?",
                    "images": ["aGVsbG8="],
                }
            ],
        )
        agent._append.assert_called_once_with(
            "You",
            "What does this error mean? [Image attached: error.png]",
        )
        agent.prompt.config.assert_called_once_with(state="disabled")
        agent.url_entry.config.assert_called_once_with(state="disabled")
        agent.workspace_button.config.assert_called_once_with(state="disabled")
        agent._clear_pending_image.assert_called_once_with()
        thread.assert_called_once()

    def test_prompt_keypresses_are_blocked_while_busy(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent.last_prompt_enter = 10.0
        agent._send = Mock()

        self.assertEqual(agent._on_prompt_enter(Mock(keysym="Return")), "break")
        agent._on_prompt_other_key(Mock(keysym="a"))

        self.assertEqual(agent.last_prompt_enter, 10.0)
        agent._send.assert_not_called()

    def test_dropped_image_is_rejected_while_busy(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent.status = Mock()
        agent.pending_image = None

        result = agent._on_image_drop(Mock(data="/tmp/image.png"))

        self.assertEqual(result, "refuse")
        self.assertIsNone(agent.pending_image)
        agent.status.set.assert_not_called()

    def test_working_status_includes_cpu_temperature_and_cpu_gpu_utilization(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent.root = Mock()
        agent.root.after.return_value = "temperature-refresh"
        agent.status = Mock()
        agent.previous_cpu_counters = (1000, 800)

        with (
            patch("app.read_system_status", return_value=(55, 60)),
            patch("app.read_cpu_counters", return_value=(1200, 900)),
        ):
            agent._update_working_status()

        agent.status.set.assert_called_once_with(
            "Working…  CPU - 55°C / CPU usage - 50% / GPU - 60% utilization"
        )
        agent.root.after.assert_called_once_with(
            2000, agent._update_working_status
        )
        self.assertEqual(agent.working_status_after, "temperature-refresh")

    def test_double_enter_sends_and_prevents_second_newline(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.last_prompt_enter = None
        agent._send = Mock()
        enter = Mock(keysym="Return")

        with patch("app.time.monotonic", side_effect=(10.0, 10.5)):
            self.assertIsNone(agent._on_prompt_enter(enter))
            self.assertEqual(agent._on_prompt_enter(enter), "break")

        agent._send.assert_called_once_with()
        self.assertIsNone(agent.last_prompt_enter)

    def test_keypad_enter_also_sends_on_second_press(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.last_prompt_enter = None
        agent._send = Mock()

        with patch("app.time.monotonic", side_effect=(10.0, 10.5)):
            self.assertIsNone(agent._on_prompt_enter(Mock(keysym="KP_Enter")))
            self.assertEqual(
                agent._on_prompt_enter(Mock(keysym="KP_Enter")), "break"
            )

        agent._send.assert_called_once_with()

    def test_non_enter_key_resets_double_enter_sequence(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.last_prompt_enter = 10.0
        agent._send = Mock()

        agent._on_prompt_other_key(Mock(keysym="a"))
        with patch("app.time.monotonic", return_value=10.2):
            self.assertIsNone(agent._on_prompt_enter(Mock(keysym="Return")))

        agent._send.assert_not_called()
        self.assertEqual(agent.last_prompt_enter, 10.2)

    def test_double_enter_after_timeout_starts_a_new_sequence(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.last_prompt_enter = 10.0
        agent._send = Mock()

        with patch("app.time.monotonic", return_value=11.1):
            self.assertIsNone(agent._on_prompt_enter(Mock(keysym="Return")))

        agent._send.assert_not_called()
        self.assertEqual(agent.last_prompt_enter, 11.1)

    def test_send_button_requires_existing_workspace_and_idle_app(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.send_button = Mock()
        agent.busy = False

        agent.workspace = None
        agent._update_send_button()
        agent.send_button.config.assert_called_with(
            state="disabled",
            bg="#d6e2d7",
            fg="#183b24",
            disabledforeground="#183b24",
        )

        with TemporaryDirectory() as folder:
            agent.workspace = Path(folder)
            agent._update_send_button()
            agent.send_button.config.assert_called_with(
                state="normal",
                bg="#2f6b3f",
                fg="#ffffff",
                disabledforeground="#183b24",
            )

            agent.busy = True
            agent._update_send_button()
            agent.send_button.config.assert_called_with(
                state="disabled",
                bg="#d6e2d7",
                fg="#183b24",
                disabledforeground="#183b24",
            )

    def test_successful_model_load_activates_model_and_starts_new_chat(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent.active_model = "llama3.1:8b"
        agent.model_selector = Mock()
        agent.url_entry = Mock()
        agent.model_choice = Mock()
        agent.new_chat_button = Mock()
        agent.send_button = Mock()
        agent.status = Mock()
        agent.workspace = Path(".")
        agent.mode_buttons = []
        agent.messages = [{"role": "user", "content": "old conversation"}]
        agent.screen_observed = True
        agent.transcript = Mock()
        agent._save_preferences = Mock()

        agent._finish_model_load("qwen3-vl:8b", "llama3.1:8b", None)

        self.assertEqual(agent.active_model, "qwen3-vl:8b")
        self.assertEqual(agent.messages[0]["role"], "system")
        self.assertFalse(agent.screen_observed)
        agent.transcript.delete.assert_called_once_with("1.0", "end")
        agent.status.set.assert_called_with("qwen3-vl:8b loaded. Ready for a new chat.")
        agent.model_selector.config.assert_called_with(state="readonly")
        agent.url_entry.config.assert_called_once_with(state="normal")
        agent._save_preferences.assert_called_once_with()

    def test_failed_model_load_restores_previous_selection(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = True
        agent.active_model = "llama3.1:8b"
        agent.model_selector = Mock()
        agent.url_entry = Mock()
        agent.model_choice = Mock()
        agent.new_chat_button = Mock()
        agent.send_button = Mock()
        agent.status = Mock()
        agent.workspace = Path(".")
        agent._append = Mock()

        agent._finish_model_load(
            "qwen3-vl:8b", "llama3.1:8b", "model not found"
        )

        agent.model_choice.set.assert_called_once_with("llama3.1:8b")
        self.assertEqual(agent.active_model, "llama3.1:8b")
        agent.url_entry.config.assert_called_once_with(state="normal")
        agent._append.assert_called_once_with("Error", "model not found")

    def test_send_does_not_submit_without_valid_workspace(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.busy = False
        agent.workspace = None
        agent.send_button = Mock()
        agent.status = Mock()
        agent._update_send_button = Mock()
        agent.prompt = Mock()
        agent._send = DesktopAgent._send.__get__(agent)

        agent._send()

        agent._update_send_button.assert_called_once_with()
        agent.status.set.assert_called_once_with(
            "Choose a valid workspace folder before sending a message."
        )
        agent.prompt.get.assert_not_called()

    def test_blocks_screen_interaction_until_screenshot(self) -> None:
        agent = DesktopAgent.__new__(DesktopAgent)
        agent.screen_observed = False
        result, images = agent._execute_tool("click", {"x": 10, "y": 20})
        self.assertIn("take a fresh screenshot", result)
        self.assertIsNone(images)

    def test_rejects_outside_write_path_before_approval(self) -> None:
        with TemporaryDirectory() as folder:
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)
            agent._request_approval = Mock()

            with self.assertRaisesRegex(ValueError, "Path must stay inside"):
                agent._execute_tool(
                    "write_file",
                    {"path": "../HelloWorld.txt", "content": "Hello, world!"},
                )

            agent._request_approval.assert_not_called()

    def test_write_approval_shows_resolved_workspace_path(self) -> None:
        with TemporaryDirectory() as folder:
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)
            agent._request_approval = Mock(return_value=False)

            result, _ = agent._execute_tool(
                "write_file",
                {"path": "HelloWorld.txt", "content": "Hello, world!"},
            )

            self.assertEqual(result, "Action denied by the user.")
            approval_args = agent._request_approval.call_args.args[1]
            self.assertEqual(approval_args["resolved_path"], str(Path(folder) / "HelloWorld.txt"))
            self.assertFalse((Path(folder) / "HelloWorld.txt").exists())

    def test_view_image_attaches_supported_image_from_workspace(self) -> None:
        image_bytes = b"\x89PNG\r\n\x1a\nsample-image"
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "test-image-1.png"
            image_path.write_bytes(image_bytes)
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)

            result, images = agent._execute_tool(
                "view_image", {"path": "test-image-1.png"}
            )

        self.assertEqual(result, "Attached image test-image-1.png for visual inspection.")
        self.assertEqual(images, [base64.b64encode(image_bytes).decode("ascii")])

    def test_view_image_rejects_unsupported_file_extension(self) -> None:
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "image.svg"
            image_path.write_text("<svg/>", encoding="utf-8")
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)

            with self.assertRaisesRegex(ValueError, "Image must use"):
                agent._execute_tool("view_image", {"path": image_path.name})

    def test_view_image_rejects_images_over_size_limit(self) -> None:
        with TemporaryDirectory() as folder:
            image_path = Path(folder) / "large.png"
            image_path.write_bytes(b"x" * (MAX_IMAGE_BYTES + 1))
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = Path(folder)

            with self.assertRaisesRegex(ValueError, "10 MB view limit"):
                agent._execute_tool("view_image", {"path": image_path.name})

    def test_view_image_rejects_workspace_escape(self) -> None:
        with TemporaryDirectory() as folder:
            workspace = Path(folder) / "workspace"
            outside = Path(folder) / "outside.png"
            workspace.mkdir()
            outside.write_bytes(b"image")
            agent = DesktopAgent.__new__(DesktopAgent)
            agent.workspace = workspace

            with self.assertRaisesRegex(ValueError, "stay inside"):
                agent._execute_tool("view_image", {"path": "../outside.png"})


if __name__ == "__main__":
    unittest.main()
