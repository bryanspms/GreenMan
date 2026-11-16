"""A local tic-tac-toe game against Green Man."""

from __future__ import annotations

import tkinter as tk


WINNING_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)


def winner(board: list[str]) -> str | None:
    for first, second, third in WINNING_LINES:
        if board[first] and board[first] == board[second] == board[third]:
            return board[first]
    return None


def choose_move(board: list[str]) -> int:
    """Choose an optimal move for O without changing the caller's board."""
    def score(position: list[str], player: str) -> int:
        result = winner(position)
        if result:
            return 1 if result == "O" else -1
        empty = [index for index, cell in enumerate(position) if not cell]
        if not empty:
            return 0
        scores = []
        for index in empty:
            position[index] = player
            scores.append(score(position, "X" if player == "O" else "O"))
            position[index] = ""
        return max(scores) if player == "O" else min(scores)

    position = board.copy()
    empty = [index for index, cell in enumerate(position) if not cell]
    if not empty or winner(position):
        raise ValueError("Cannot choose a move in a finished game.")
    best_move = empty[0]
    best_score = -2
    for index in empty:
        position[index] = "O"
        move_score = score(position, "X")
        position[index] = ""
        if move_score > best_score:
            best_move, best_score = index, move_score
    return best_move


class TicTacToeDialog:
    def __init__(self, parent: tk.Tk, colors: dict[str, str]) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("Tic-tac-toe")
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.configure(bg=colors["background"])
        self.board = [""] * 9
        self.game_over = False
        self.status = tk.StringVar(master=self.window, value="You are X. Your turn.")
        tk.Label(self.window, textvariable=self.status).pack(padx=12, pady=(12, 8))
        grid = tk.Frame(self.window)
        grid.pack(padx=12)
        self.cells: list[tk.Button] = []
        for index in range(9):
            button = tk.Button(
                grid, text="", width=4, height=2, font=("TkDefaultFont", 18, "bold"),
                command=lambda cell=index: self.play(cell),
                bg=colors["input"], fg=colors["text"],
                activebackground=colors["green_selected"],
            )
            button.grid(row=index // 3, column=index % 3, padx=2, pady=2)
            self.cells.append(button)
        controls = tk.Frame(self.window)
        controls.pack(pady=12)
        self.new_game_button = tk.Button(controls, text="New game", command=self.reset)
        self.new_game_button.pack(side=tk.LEFT, padx=4)
        self.close_button = tk.Button(controls, text="Close", command=self.window.destroy)
        self.close_button.pack(side=tk.LEFT, padx=4)
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.grab_set()
        self.window.focus_set()

    def play(self, index: int) -> None:
        if self.game_over or self.board[index]:
            return
        self._place(index, "X")
        if self._finish_if_needed():
            return
        self._place(choose_move(self.board), "O")
        self._finish_if_needed()

    def _place(self, index: int, mark: str) -> None:
        self.board[index] = mark
        self.cells[index].config(text=mark, state=tk.DISABLED)

    def _finish_if_needed(self) -> bool:
        result = winner(self.board)
        if result:
            self.status.set("You win!" if result == "X" else "Green Man wins!")
        elif all(self.board):
            self.status.set("It's a draw!")
        else:
            self.status.set("You are X. Your turn.")
            return False
        self.game_over = True
        for cell in self.cells:
            cell.config(state=tk.DISABLED)
        return True

    def reset(self) -> None:
        self.board = [""] * 9
        self.game_over = False
        self.status.set("You are X. Your turn.")
        for cell in self.cells:
            cell.config(text="", state=tk.NORMAL)
