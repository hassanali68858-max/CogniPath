from contextlib import asynccontextmanager
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine

from .db import Settings, get_preferences, save_preferences
from .models import Preferences


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.tokens = settings.event_user_tokens
    app.state.engine = create_engine(settings.event_database_url, pool_pre_ping=True)
    try:
        yield
    finally:
        app.state.engine.dispose()


app = FastAPI(title="CogniPath Event Agent", lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)


def authorize(
    user_id: str,
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    expected = request.app.state.tokens.get(user_id)
    if not expected or credentials is None or not compare_digest(
        credentials.credentials.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/preferences/{user_id}", dependencies=[Depends(authorize)])
def read_preferences(user_id: str, request: Request) -> Preferences:
    with request.app.state.engine.connect() as conn:
        values = get_preferences(conn, user_id)
    if values is None:
        raise HTTPException(404, "Event preferences not found")
    return values


@app.put("/preferences/{user_id}", dependencies=[Depends(authorize)])
def update_preferences(user_id: str, values: Preferences, request: Request) -> Preferences:
    with request.app.state.engine.begin() as conn:
        save_preferences(conn, user_id, values)
    return values
