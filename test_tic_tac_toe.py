import tkinter as tk
import unittest
import sys
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from tkinterdnd2 import TkinterDnD

from app import DesktopAgent, THEME_COLORS
from tic_tac_toe import TicTacToeDialog, choose_move, winner


class TicTacToeLogicTests(unittest.TestCase):
    def test_all_winning_lines_and_draw(self) -> None:
        for line in ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6),
                     (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)):
            with self.subTest(line=line):
                board = [""] * 9
                for index in line:
                    board[index] = "X"
                self.assertEqual(winner(board), "X")
        self.assertIsNone(winner(list("XOXXOOOXX")))

    def test_opponent_wins_and_blocks_without_mutating_board(self) -> None:
        for board, expected in (
            (["O", "O", "", "X", "X", "", "", "", ""], 2),
            (["X", "X", "", "", "O", "", "", "", ""], 2),
        ):
            with self.subTest(board=board):
                original = board.copy()
                self.assertEqual(choose_move(board), expected)
                self.assertEqual(board, original)
        with self.assertRaises(ValueError):
            choose_move(list("XOXXOOOXX"))

    def test_opponent_cannot_lose_against_any_player_sequence(self) -> None:
        def explore(board: list[str]) -> None:
            for index, cell in enumerate(board):
                if cell:
                    continue
                after_player = board.copy()
                after_player[index] = "X"
                self.assertNotEqual(winner(after_player), "X")
                if all(after_player):
                    continue
                after_player[choose_move(after_player)] = "O"
                if not winner(after_player) and not all(after_player):
                    explore(after_player)

        explore([""] * 9)


class TicTacToeUITests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = TkinterDnD.Tk()
        except tk.TclError as error:
            self.skipTest(f"No display available: {error}")
        self.addCleanup(self.root.destroy)

    def test_dialog_plays_resets_and_closes(self) -> None:
        game = TicTacToeDialog(self.root, THEME_COLORS)
        self.assertEqual(game.window.grab_current(), game.window)
        game.cells[0].invoke()
        self.assertEqual(game.board.count("X"), 1)
        self.assertEqual(game.board.count("O"), 1)
        self.assertEqual(str(game.cells[0].cget("state")), "disabled")
        for index in range(9):
            if not game.game_over and not game.board[index]:
                game.cells[index].invoke()
        self.assertTrue(game.game_over)
        self.assertTrue(all(str(cell.cget("state")) == "disabled" for cell in game.cells))
        game.new_game_button.invoke()
        self.assertEqual(game.board, [""] * 9)
        self.assertTrue(all(str(cell.cget("state")) == "normal" for cell in game.cells))
        game.close_button.invoke()
        self.assertIsNone(self.root.grab_current())

    def test_game_selector_opens_modal_and_close_returns_to_main(self) -> None:
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)), patch.object(
            DesktopAgent, "_refresh_ollama_models"
        ), patch.object(DesktopAgent, "_begin_model_load"):
            agent = DesktopAgent(self.root)
            self.addCleanup(self._cancel_callbacks)
            self.assertEqual(agent.game_choice.get(), "None")
            self.assertFalse(agent.pong_study_enabled.get())
            self.assertEqual(
                tuple(agent.game_selector.cget("values")), ("None", "Tic-Tac-Toe", "Pong")
            )
            agent.busy = True
            agent._update_send_button()
            self.assertEqual(str(agent.game_selector.cget("state")), "disabled")
            self.assertEqual(str(agent.pong_study_checkbox.cget("state")), "disabled")
            agent.game_choice.set("Tic-Tac-Toe")
            agent._on_game_selected()
            self.assertIsNone(self.root.grab_current())
            agent.busy = False
            agent._update_send_button()
            self.assertEqual(str(agent.game_selector.cget("state")), "readonly")
            self.assertEqual(str(agent.pong_study_checkbox.cget("state")), "normal")
            agent.game_selector.current(1)
            agent.game_selector.event_generate("<<ComboboxSelected>>")
            self.root.update()
            self.assertEqual(agent.game_choice.get(), "None")
            game_window = self.root.grab_current()
            self.assertIsNotNone(game_window)
            self.assertEqual(game_window.title(), "Tic-tac-toe")
            game_window.destroy()
            self.assertIsNone(self.root.grab_current())
            self.assertTrue(self.root.winfo_exists())

    def test_pong_selection_launches_with_same_python_and_reports_errors(self) -> None:
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)), patch.object(
            DesktopAgent, "_refresh_ollama_models"
        ), patch.object(DesktopAgent, "_begin_model_load"):
            agent = DesktopAgent(self.root)
            self.addCleanup(self._cancel_callbacks)
            process = Mock()
            process.communicate.return_value = (None, "No module named pygame")
            process.returncode = 1
            with patch("app.subprocess.Popen", return_value=process) as popen, patch(
                "app.threading.Thread"
            ) as thread:
                agent.game_selector.current(2)
                agent.game_selector.event_generate("<<ComboboxSelected>>")
                self.assertEqual(agent.game_choice.get(), "None")
                self.assertEqual(
                    popen.call_args.args[0],
                    [sys.executable, "-u", str(Path(__file__).with_name("pong.py"))],
                )
                thread.return_value.start.assert_called_once()
                agent.game_choice.set("Pong")
                agent._on_game_selected()
                popen.assert_called_once()
                self.assertIn("already running", agent.status.get())
                agent._wait_for_pong(process)
                self.root.after_cancel(agent._pong_poll_after)
                agent._poll_pong()
                self.assertIn("No module named pygame", agent.status.get())
                self.assertIsNone(agent._pong_process)
            with patch("app.subprocess.Popen", side_effect=OSError("cannot launch")):
                agent.game_choice.set("Pong")
                agent._on_game_selected()
                self.assertIn("cannot launch", agent.status.get())
                self.assertEqual(agent.game_choice.get(), "None")

    def test_pong_study_is_opt_in_and_routes_send_to_study_worker(self) -> None:
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)), patch.object(
            DesktopAgent, "_refresh_ollama_models"
        ), patch.object(DesktopAgent, "_begin_model_load"):
            agent = DesktopAgent(self.root)
            self.addCleanup(self._cancel_callbacks)
            agent.workspace = Path(folder)
            agent.tool_mode.set("Desktop control")
            agent._supports_visual_tools = Mock(return_value=True)
            agent.capability_check_pending = False
            agent.wayland_desktop = Mock()
            process = Mock(pid=42)
            process.poll.return_value = None
            agent._pong_process = process
            agent.pong_study_enabled.set(True)
            agent.prompt.insert("1.0", "Play Pong")
            with patch("app.threading.Thread") as thread:
                agent._send()
            self.assertEqual(thread.call_args.kwargs["target"], agent._run_pong_study)
            self.assertIs(thread.call_args.kwargs["args"][2], process)
            thread.return_value.start.assert_called_once()

    @unittest.skipUnless(importlib.util.find_spec("pygame"), "Pong requires pygame")
    def test_pong_subprocess_starts_and_exit_is_observed(self) -> None:
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)), patch.object(
            DesktopAgent, "_refresh_ollama_models"
        ), patch.object(DesktopAgent, "_begin_model_load"), patch.dict(
            "os.environ", {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
        ):
            agent = DesktopAgent(self.root)
            self.addCleanup(self._cancel_callbacks)
            agent.game_choice.set("Pong")
            agent._on_game_selected()
            process = agent._pong_process
            self.assertIsNotNone(process)
            try:
                self.root.after(500, self.root.quit)
                self.root.mainloop()
                self.assertIsNone(process.poll(), agent.status.get())
                process.terminate()
                self.root.after(500, self.root.quit)
                self.root.mainloop()
                self.assertIsNone(agent._pong_process)
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

    def _cancel_callbacks(self) -> None:
        for callback in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.after_cancel(callback)


if __name__ == "__main__":
    unittest.main()
