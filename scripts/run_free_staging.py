"""Run the staging API and RQ worker in one free Render web service."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterable


def stop_processes(processes: Iterable[subprocess.Popen[object]]) -> None:
    active = [process for process in processes if process.poll() is None]
    for process in active:
        process.terminate()

    deadline = time.monotonic() + 10
    for process in active:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main() -> int:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)

    worker = subprocess.Popen([sys.executable, "-m", "app.workers.run"])
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.environ.get("PORT", "8000"),
        ]
    )
    processes = [worker, api]

    def handle_signal(signum: int, _frame: object) -> None:
        stop_processes(processes)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while True:
            for process in processes:
                exit_code = process.poll()
                if exit_code is not None:
                    stop_processes(processes)
                    return exit_code if exit_code != 0 else 1
            time.sleep(1)
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
