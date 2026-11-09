"""Speak through a dedicated Speech Dispatcher client controlled by signals."""

import signal
import sys
import threading
from collections import deque


def main() -> int:
    try:
        import speechd
    except ImportError:
        print(
            "error:Speech Dispatcher requires the system python3-speechd package.",
            flush=True,
        )
        return 1

    commands: deque[int] = deque()
    finished = threading.Event()
    for sig in (signal.SIGUSR1, signal.SIGUSR2, signal.SIGTERM):
        signal.signal(sig, lambda number, _frame: commands.append(number))
    client = None
    try:
        text = sys.stdin.read()
        client = speechd.SSIPClient("greenman")

        def notify(event: str, **_kwargs: object) -> None:
            if event in ("begin", "pause", "resume"):
                print(event, flush=True)
            elif event in ("end", "cancel"):
                finished.set()

        client.block_begin()
        client.speak(text, callback=notify)
        client.block_end()
        while not finished.wait(0.05):
            while commands:
                command = commands.popleft()
                if command == signal.SIGTERM:
                    client.cancel()
                    return 0
                if command == signal.SIGUSR1:
                    client.pause()
                elif command == signal.SIGUSR2:
                    client.resume()
        return 0
    except (OSError, RuntimeError, speechd.SSIPError, speechd.SSIPResponseError) as error:
        print(f"error:{error}", flush=True)
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
