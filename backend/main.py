"""CogniPath backend (development version).

For now it serves the Planner API plus a few demo helpers, and allows the
Next.js frontend to call it. Other agents' endpoints will be added here later.

Run from the repository root:

    uvicorn backend.main:app --reload            # http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import os

from fastapi.middleware.cors import CORSMiddleware

from agents.planner_agent.api import create_app

from .demo import router as demo_router


def build_app():
    app = create_app()
    app.title = "CogniPath Backend"
    origins = os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(demo_router)
    return app


app = build_app()
