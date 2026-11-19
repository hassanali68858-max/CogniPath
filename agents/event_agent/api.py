from contextlib import asynccontextmanager
from hmac import compare_digest
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image
from sqlalchemy import create_engine, func, select

from .assessment import with_inferred_language
from .collectors.posters import MAX_UPLOAD_BYTES, collect_posters, prepare_image
from .db import AGENT_DIR, Settings, events, get_preferences, poster_uploads, runs, save_preferences, sources
from .llm import ModelUnavailable
from .models import EventCandidate, EventCatalog, IngestionRequest, Preferences, PublishRequest, ResetRequest
from .recommendations import list_recommendations, match_posters, publish, refresh
from .service import reset_event_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.tokens = settings.event_user_tokens
    app.state.operator_token = settings.event_operator_token
    app.state.planner_url = settings.event_planner_url
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
    check_token(expected, credentials)


def authorize_operator(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    check_token(request.app.state.operator_token, credentials)


def token_matches(expected, credentials) -> bool:
    return bool(expected and credentials and compare_digest(
        credentials.credentials.encode(), expected.get_secret_value().encode()
    ))


def check_token(expected, credentials) -> None:
    if not token_matches(expected, credentials):
        raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "Bearer"})


def authorize_catalog(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    tokens = request.app.state.tokens.values()
    if any(token_matches(token, credentials) for token in tokens):
        return
    check_token(request.app.state.operator_token, credentials)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def event_page():
    return FileResponse(AGENT_DIR / "events.html", media_type="text/html")


@app.post("/admin/reset", dependencies=[Depends(authorize_operator)])
def reset_database(request: Request, body: ResetRequest):
    with request.app.state.engine.begin() as conn:
        if not reset_event_data(conn):
            raise HTTPException(409, "An ingestion or catalog update is active. Try again after it finishes.")
    return {"status": "reset"}


@app.get("/events", dependencies=[Depends(authorize_catalog)])
def list_events(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EventCatalog:
    with request.app.state.engine.connect() as conn:
        total = conn.scalar(select(func.count()).select_from(events))
        rows = conn.execute(
            select(events.c.id, events.c.details, events.c.knowledge).order_by(events.c.id).limit(limit).offset(offset)
        ).mappings()
        return EventCatalog(total=total, limit=limit, offset=offset, events=[
            {"id": row["id"], "event": with_inferred_language(
                EventCandidate.model_validate(row["details"]), row["knowledge"]
            )} for row in rows
        ])


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


@app.post("/ingestion/runs", status_code=202, dependencies=[Depends(authorize_operator)])
def queue_ingestion(request: Request, body: IngestionRequest | None = None):
    requested = set(body.source_keys) if body else set()
    with request.app.state.engine.begin() as conn:
        enabled = set(conn.scalars(select(sources.c.key).where(sources.c.enabled.is_(True))))
        if requested - enabled:
            raise HTTPException(422, "Unknown or disabled source")
        selected = sorted(requested or enabled)
        if not selected:
            raise HTTPException(409, "No enabled sources")
        run_id = uuid4().hex
        conn.execute(runs.insert().values(
            id=run_id, source_keys=selected, status="queued", results={}, limit=body.limit if body else None,
        ))
    return {"run_id": run_id, "status": "queued"}


@app.get("/ingestion/runs/{run_id}", dependencies=[Depends(authorize_operator)])
def ingestion_status(run_id: str, request: Request):
    with request.app.state.engine.connect() as conn:
        run = conn.execute(select(runs).where(runs.c.id == run_id)).mappings().one_or_none()
    if run is None:
        raise HTTPException(404, "Ingestion run not found")
    return dict(run)


@app.get("/ingestion/runs", dependencies=[Depends(authorize_operator)])
def recent_ingestion_runs(request: Request):
    with request.app.state.engine.connect() as conn:
        recent = conn.execute(select(runs).order_by(runs.c.created_at.desc()).limit(20)).mappings()
        return [dict(run) for run in recent]


def deliver(request: Request, user_id: str, ids: list[str] | None = None):
    try:
        with httpx.Client(base_url=request.app.state.planner_url, timeout=10) as client:
            with request.app.state.engine.begin() as conn:
                return publish(conn, client, user_id, ids)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@app.get("/recommendations/{user_id}", dependencies=[Depends(authorize)])
def read_recommendations(user_id: str, request: Request):
    with request.app.state.engine.connect() as conn:
        return list_recommendations(conn, user_id)


@app.post("/recommendations/{user_id}/refresh", dependencies=[Depends(authorize)])
def refresh_recommendations(user_id: str, request: Request):
    try:
        with httpx.Client(timeout=45) as client, request.app.state.engine.begin() as conn:
            auto_publish = refresh(conn, user_id, client, Settings())
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ModelUnavailable as error:
        raise HTTPException(503, str(error)) from error
    delivery = deliver(request, user_id) if auto_publish else None
    return {"recommendations": read_recommendations(user_id, request), "delivery": delivery}


@app.post("/recommendations/{user_id}/publish", dependencies=[Depends(authorize)])
def publish_recommendations(user_id: str, request: Request, body: PublishRequest | None = None):
    return deliver(request, user_id, body.recommendation_ids if body else None)


@app.post("/poster-analysis/{user_id}", dependencies=[Depends(authorize)])
def analyze_poster(
    user_id: str,
    request: Request,
    image: Annotated[UploadFile, File()],
    share_events: Annotated[bool, Form()] = False,
):
    engine = request.app.state.engine
    settings = Settings()
    key = settings.poster_agent_key or settings.llm_api_key
    if not key:
        raise HTTPException(503, "Set POSTER_AGENT_KEY in the Event Agent .env")
    with engine.connect() as conn:
        if get_preferences(conn, user_id) is None:
            raise HTTPException(404, "Event preferences not found")
    data = image.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image must be at most 10 MB")
    try:
        prepared = prepare_image(data)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "Use a valid JPEG, PNG, or WebP image of at most 30 megapixels") from error

    upload_id = uuid4().hex
    with engine.begin() as conn:
        conn.execute(poster_uploads.insert().values(id=upload_id, user_id=user_id, share_events=share_events))
    try:
        with httpx.Client(timeout=45) as client:
            candidates = collect_posters(
                client, prepared, key.get_secret_value(),
                settings.poster_agent_model or settings.event_vision_model, settings.poster_agent_base_url,
            )
    except httpx.TimeoutException as error:
        raise HTTPException(504, "Poster analysis timed out. Please retry.") from error
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(502, "The vision provider could not analyze this image") from error
    try:
        with httpx.Client(timeout=45) as client, engine.begin() as conn:
            matched, shared, auto_publish = match_posters(conn, user_id, candidates, share_events, client, settings)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ModelUnavailable as error:
        raise HTTPException(503, str(error)) from error
    delivery = deliver(request, user_id, sorted(matched)) if auto_publish and matched else None
    results = read_recommendations(user_id, request)
    return {
        "upload_id": upload_id,
        "extracted_count": len(candidates),
        "shared_count": shared,
        "recommendations": [row for row in results if row["id"] in matched],
        "delivery": delivery,
    }
