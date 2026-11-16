import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

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

    def test_main_button_opens_modal_and_close_returns_to_main(self) -> None:
        with TemporaryDirectory() as folder, patch(
            "app.preferences_path", return_value=Path(folder) / "preferences.json"
        ), patch("app.piper_voice_directory", return_value=Path(folder)), patch.object(
            DesktopAgent, "_refresh_ollama_models"
        ), patch.object(DesktopAgent, "_begin_model_load"):
            agent = DesktopAgent(self.root)
            self.addCleanup(self._cancel_callbacks)
            self.assertEqual(agent.play_game_button.cget("text"), "Play game")
            agent.busy = True
            agent._update_send_button()
            self.assertEqual(str(agent.play_game_button.cget("state")), "disabled")
            agent.play_game_button.invoke()
            self.assertIsNone(self.root.grab_current())
            agent.busy = False
            agent._update_send_button()
            self.assertEqual(str(agent.play_game_button.cget("state")), "normal")
            agent.play_game_button.invoke()
            game_window = self.root.grab_current()
            self.assertIsNotNone(game_window)
            self.assertEqual(game_window.title(), "Tic-tac-toe")
            game_window.destroy()
            self.assertIsNone(self.root.grab_current())
            self.assertTrue(self.root.winfo_exists())

    def _cancel_callbacks(self) -> None:
        for callback in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.after_cancel(callback)


if __name__ == "__main__":
    unittest.main()
