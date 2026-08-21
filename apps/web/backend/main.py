from __future__ import annotations

from pathlib import Path


def app_status() -> dict[str, object]:
    """Small placeholder until the FastAPI app is wired.

    Keeping this dependency-free lets the scaffold be tested before FastAPI and
    frontend dependencies are installed.
    """

    return {
        "name": "flight-log-reviewer-pro-web",
        "status": "scaffolded",
        "root": str(Path(__file__).resolve().parents[2]),
    }


if __name__ == "__main__":
    print(app_status())
