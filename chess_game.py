import tkinter as tk
from tkinter import messagebox
import chess

# Solid glyphs for fill; outline glyphs layered on top for white pieces
SOLID_SYMBOLS = {
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
}
OUTLINE_SYMBOLS = {
    'p': '♙', 'n': '♘', 'b': '♗', 'r': '♖', 'q': '♕', 'k': '♔'
}

SQUARE_SIZE = 64
BORDER_SIZE = 28

LIGHT_SQUARE = "#EEEED2"
DARK_SQUARE = "#769656"        # Fits the "Green Man" theme
SELECTED_COLOR = "#F6F669"
LEGAL_MOVE_COLOR = "#BACA44"
LAST_MOVE_LIGHT = "#F5F682"
LAST_MOVE_DARK = "#B9CA43"
BOARD_BG = "#2F352B"
LABEL_COLOR = "#EAECE6"


class ChessGame(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chess")
        self.resizable(False, False)

        # Chess engine handles all rules, turns, and move validation
        self.engine = chess.Board()
        self.selected_square = None

        # Title
        title_label = tk.Label(self, text="Green Man - Chess Game", font=("Arial", 16, "bold"))
        title_label.pack(pady=(15, 5))

        # Status bar (shows whose turn it is or if someone is in check)
        self.status_label = tk.Label(self, text="White's Turn", font=("Arial", 12))
        self.status_label.pack(pady=(0, 10))

        # Canvas for board + coordinate border
        canvas_size = (SQUARE_SIZE * 8) + (BORDER_SIZE * 2)
        self.canvas = tk.Canvas(
            self,
            width=canvas_size,
            height=canvas_size,
            bg=BOARD_BG,
            highlightthickness=2,
            highlightbackground="#111111"
        )
        self.canvas.pack(padx=20, pady=5)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        # New Game button
        reset_button = tk.Button(self, text="New Game", command=self.reset_game, font=("Arial", 11))
        reset_button.pack(pady=(10, 6))

        # Legal moves display (fixed height so window size stays constant)
        self.legal_moves_label = tk.Label(
            self,
            text="",
            font=("DejaVu Sans Mono", 9),
            wraplength=560,
            justify=tk.LEFT,
            height=4,
            anchor=tk.NW,
            padx=20,
        )
        self.legal_moves_label.pack(fill=tk.X, pady=(0, 2))

        # Draw / fifty-move info display at the very bottom
        self.draw_info_label = tk.Label(
            self,
            text="",
            font=("Arial", 10),
            justify=tk.LEFT,
            anchor=tk.W,
            padx=20,
        )
        self.draw_info_label.pack(fill=tk.X, pady=(0, 10))
        self.update_board()

    def draw_coordinates(self):
        """Draw a-h file labels and 1-8 rank labels around the board"""
        files = "abcdefgh"
        board_end = BORDER_SIZE + (SQUARE_SIZE * 8)

        for col, file_char in enumerate(files):
            x = BORDER_SIZE + (col * SQUARE_SIZE) + (SQUARE_SIZE // 2)
            # Top and bottom file labels
            self.canvas.create_text(
                x, BORDER_SIZE // 2, text=file_char,
                fill=LABEL_COLOR, font=("Arial", 11, "bold")
            )
            self.canvas.create_text(
                x, board_end + (BORDER_SIZE // 2), text=file_char,
                fill=LABEL_COLOR, font=("Arial", 11, "bold")
            )

        for row in range(8):
            rank_char = str(8 - row)
            y = BORDER_SIZE + (row * SQUARE_SIZE) + (SQUARE_SIZE // 2)
            # Left and right rank labels
            self.canvas.create_text(
                BORDER_SIZE // 2, y, text=rank_char,
                fill=LABEL_COLOR, font=("Arial", 11, "bold")
            )
            self.canvas.create_text(
                board_end + (BORDER_SIZE // 2), y, text=rank_char,
                fill=LABEL_COLOR, font=("Arial", 11, "bold")
            )

    def update_board(self):
        """Redraw coordinates, squares, and pieces based on the current engine state"""
        self.canvas.delete("all")
        self.draw_coordinates()

        legal_targets = set()
        if self.selected_square is not None:
            for move in self.engine.legal_moves:
                if move.from_square == self.selected_square:
                    legal_targets.add(move.to_square)

        last_move = self.engine.peek() if self.engine.move_stack else None

        for row in range(8):
            for col in range(8):
                sq = chess.square(col, 7 - row)
                x1 = BORDER_SIZE + (col * SQUARE_SIZE)
                y1 = BORDER_SIZE + (row * SQUARE_SIZE)
                x2 = x1 + SQUARE_SIZE
                y2 = y1 + SQUARE_SIZE
                is_light = (row + col) % 2 == 0

                # Choose square background color
                if sq == self.selected_square:
                    bg = SELECTED_COLOR
                elif sq in legal_targets:
                    bg = LEGAL_MOVE_COLOR
                elif last_move and sq in (last_move.from_square, last_move.to_square):
                    bg = LAST_MOVE_LIGHT if is_light else LAST_MOVE_DARK
                else:
                    bg = LIGHT_SQUARE if is_light else DARK_SQUARE

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg, outline="")

                # Draw piece
                piece = self.engine.piece_at(sq)
                if piece:
                    cx = x1 + (SQUARE_SIZE // 2)
                    cy = y1 + (SQUARE_SIZE // 2)
                    key = piece.symbol().lower()

                    if piece.color == chess.WHITE:
                        # Solid white fill + crisp black outline on top
                        self.canvas.create_text(
                            cx, cy, text=SOLID_SYMBOLS[key],
                            fill="#FFFFFF", font=("DejaVu Sans", 34)
                        )
                        self.canvas.create_text(
                            cx, cy, text=OUTLINE_SYMBOLS[key],
                            fill="#111111", font=("DejaVu Sans", 34)
                        )
                    else:
                        self.canvas.create_text(
                            cx, cy, text=SOLID_SYMBOLS[key],
                            fill="#111111", font=("DejaVu Sans", 34)
                        )

        # Update status text
        turn_text = "White's Turn" if self.engine.turn == chess.WHITE else "Black's Turn"
        if self.engine.is_check():
            turn_text += " — CHECK!"
        self.status_label.config(text=turn_text)
        if hasattr(self, "legal_moves_label"):
            moves = list(dict.fromkeys(
                f"{m.uci()[:2]}-{m.uci()[2:4]}" for m in self.engine.legal_moves
            ))
            moves_text = ", ".join(moves) if moves else "None"
            self.legal_moves_label.config(text=f"Legal moves: {moves_text}")

        # Bottom info: moves remaining until 50-move-rule draw.
        # NOTE: Stalemate itself has no countdown - it depends on position,
        # not a clock. The only "moves remaining" draw clock is the
        # 50-move rule (100 half-moves without a pawn move or capture).
        if hasattr(self, "draw_info_label"):
            half = self.engine.halfmove_clock
            rem_half = 100 - half
            rem_full = (rem_half + 1) // 2  # ceil(rem_half / 2)
            info = f"50-move draw in: {rem_full} moves ({rem_half} half-moves)  |  Halfmove clock: {half}/100"
            if self.engine.can_claim_fifty_moves():
                info += "  — 50-move draw can be claimed!"
            if self.engine.is_seventyfive_moves():
                info += "  — 75-move auto-draw!"
            # Helpful extra: repetition status (also leads to draw, but no fixed countdown)
            if self.engine.is_repetition(3):
                info += "  |  Threefold repetition!"
            elif self.engine.is_repetition(2):
                info += "  |  Same position twice (one more = claimable draw)"
            self.draw_info_label.config(text=info)

    def on_canvas_click(self, event):
        """Translate pixel click coordinates into board row/col"""
        col = (event.x - BORDER_SIZE) // SQUARE_SIZE
        row = (event.y - BORDER_SIZE) // SQUARE_SIZE

        # Ignore clicks on the coordinate border
        if 0 <= row < 8 and 0 <= col < 8:
            self.on_square_click(row, col)

    def on_square_click(self, row, col):
        """Handle selecting pieces and making moves"""
        if self.engine.is_game_over():
            return

        clicked_sq = chess.square(col, 7 - row)
        piece = self.engine.piece_at(clicked_sq)

        # If a square is already selected, try to move there
        if self.selected_square is not None:
            if clicked_sq == self.selected_square:
                self.selected_square = None
                self.update_board()
                return

            if piece and piece.color == self.engine.turn:
                self.selected_square = clicked_sq
                self.update_board()
                return

            # Attempt the move (auto-promotes pawns to Queen when reaching the back rank)
            move = chess.Move(self.selected_square, clicked_sq)
            promo_move = chess.Move(self.selected_square, clicked_sq, promotion=chess.QUEEN)

            if promo_move in self.engine.legal_moves:
                move = promo_move

            if move in self.engine.legal_moves:
                self.engine.push(move)
                self.selected_square = None
                self.update_board()
                self.check_game_over()
                return
            else:
                self.selected_square = None
                self.update_board()
                return

        # No square selected yet: select if it's the current player's piece
        if piece and piece.color == self.engine.turn:
            self.selected_square = clicked_sq
            self.update_board()

    def check_game_over(self):
        """Announce checkmate or draw conditions"""
        if not self.engine.is_game_over():
            return

        if self.engine.is_checkmate():
            winner = "Black" if self.engine.turn == chess.WHITE else "White"
            msg = f"Checkmate! {winner} wins!"
        elif self.engine.is_stalemate():
            msg = "Draw by stalemate."
        elif self.engine.is_insufficient_material():
            msg = "Draw due to insufficient material."
        else:
            msg = "Game over — Draw."

        self.status_label.config(text=msg)
        messagebox.showinfo("Game Over", msg)

    def reset_game(self):
        """Reset the board for a new game"""
        self.engine.reset()
        self.selected_square = None
        self.update_board()


def launch_chess():
    chess_window = ChessGame()
    chess_window.mainloop()


if __name__ == "__main__":
    launch_chess()