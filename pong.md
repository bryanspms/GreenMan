# Pong

Pong is a standalone, local two-player game in [pong.py](./pong.py). Both
players use the same keyboard. It runs separately from Green Man and does not
require Ollama.

## Requirements and launch

Use Python with [Pygame](https://www.pygame.org/) and
[Pillow](https://pillow.readthedocs.io/) installed. Pillow is included in Green
Man's requirements; Pygame is an optional dependency.

From the project directory, install the packages in the Python environment you
want to use, then launch the game:

```bash
python -m pip install pygame "Pillow>=10.0.0"
python pong.py
```

Alternatively, select **Pong** from Green Man's **Play game** dropdown.
Pygame and Pillow must be installed in the same Python environment Green Man
uses. Pong opens in a separate 800-by-600 window and needs a graphical desktop
session. Close it before launching another Pong game.

## Controls

| Key | Action |
| --- | --- |
| W / S | Move the left paddle up / down |
| I / K | Move the right paddle up / down |
| Left / Right arrow | Change speed before starting or after a match |
| Space | Start, pause, or resume the match; start a new match after the result |
| Escape | Quit and close the window |

You can also close the game using the window's close button.

## Playing and scoring

1. On the start screen, choose a speed with the arrow keys if desired, then
   press Space. The default is **1x**.
2. Keep the ball in play with your paddle. If it passes one paddle and leaves
   that side of the screen, the player on the opposite side earns one point.
   Press Space to pause or resume; the ball and paddles remain in place while
   paused. A short tail behind the ball shows its current direction of travel.
3. The score and number of balls remaining appear at the top. After each
   point, the ball returns to the horizontal center at a random vertical
   position and play continues automatically. The first serve of each match
   also starts at a random vertical position.
4. A match ends after **11 balls**. The player with the higher score wins.
   The result remains on screen until you press Space to play again or quit.

The new match resets the scores, ball, and paddles. The selected speed remains
in effect unless you change it on the result screen.

## Speed

The available speeds are **0.1x**, **0.5x**, **1x**, and **1.5x**. The setting affects
both the ball and the paddles. Choose it on the start or result screen; it
cannot be changed during a match.

## Desktop control experiments

For an experimental model-controlled right paddle on GNOME Wayland:

1. Install or update and reload Green Man's GNOME Shell window helper as
   described in the [README](./README.md#gnome-wayland-window-control-optional).
2. Select a local Ollama model that supports both vision and tools, and choose
   **Desktop control**. Start Pong from Green Man's **Play game** selector,
   select **0.5x**, and press Space. Place the entire Pong window on the
   monitor you will share.
3. Check **AI Pong study**, enter a message, and press **Send**. Approve the
   Wayland screen-sharing and remote-interaction prompts if requested. The
   study brings Pong forward and sends an enlarged crop of its window to the
   model, which chooses I, K, or a short wait. The transcript
   shows the model's description of what it sees when provided; this is its
   own observation, not verified game state. Moves are skipped if the model
   reports that either the ball or the right paddle is not visible. Each key
   action requires the normal desktop approval unless approvals have been
   remembered.
4. Green Man checks the Pong window title and process ID, reactivates it after
   approval, and checks focus before and after each key hold. Click **Stop**
   to end the study; if an approval dialog is open, deny the action to stop.
   Uncheck **AI Pong study** to return to ordinary Desktop control.

The focus checks cannot eliminate the small possibility of focus changing
between a check and keyboard input; avoid switching windows during a hold.
Holds are limited to half a second and are released on cancellation. The study
stops on denial, model errors, unavailable focus checks, or a closed Pong
window. It does not automatically restart a finished match; press Stop when
you are done. The model may fail to recognize the game, choose poor moves, or
respond too slowly even at 0.5x. A sent key does not prove a successful move.
Keep the entire Pong window on the shared monitor and unobscured. On a
multi-monitor desktop, the portal must report which monitor is shared; otherwise
the study stops rather than cropping an unverified region.

## Tests

With Pygame and Pillow installed, run the focused tests from the project root:

```bash
python -m unittest -v test_pong test_pong_study
```

The tests use Pygame's dummy video driver and cover controls, movement,
scoring, the 11-ball result, restart, and Escape.
