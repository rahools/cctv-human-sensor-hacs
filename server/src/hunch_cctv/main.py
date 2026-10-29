from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from . import __version__
from .inference import Engine, HunchEngine, InferenceBusyError, InferenceNotReadyError
from .settings import Settings

IMAGE_TYPES = {"image/jpeg", "image/png"}


def create_app(engine: Engine | None = None, settings: Settings | None = None) -> FastAPI:
    config = settings or Settings.from_env()
    inference = engine or HunchEngine(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await inference.start()
        app.state.server_id = config.server_id()
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            await inference.close()

    app = FastAPI(title="Hunch CCTV", version=__version__, lifespan=lifespan)
    app.state.engine = inference
    app.state.settings = config
    app.state.ready = False

    async def authenticated(authorization: str | None = Header(default=None)) -> None:
        if config.token is None:
            return
        expected = f"Bearer {config.token}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    @app.get("/healthz")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/readyz")
    async def ready() -> Response:
        if not app.state.ready or not inference.ready:
            return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(status_code=status.HTTP_200_OK)

    @app.get("/v1/status", dependencies=[Depends(authenticated)])
    async def server_status() -> dict[str, str | bool]:
        return {
            "server_id": app.state.server_id,
            "version": __version__,
            "model": "embeddinggemma-2",
            "ready": app.state.ready and inference.ready,
        }

    @app.post("/v1/detections/human", dependencies=[Depends(authenticated)])
    async def detect_human(
        request: Request,
        x_decision_threshold: float | None = Header(default=None),
    ) -> dict[str, bool | float]:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in IMAGE_TYPES:
            raise HTTPException(status_code=415, detail="Content-Type must be image/jpeg or image/png")
        length = request.headers.get("content-length")
        if length is not None and int(length) > config.max_body_bytes:
            raise HTTPException(status_code=413, detail="Image is too large")
        threshold = config.default_threshold if x_decision_threshold is None else x_decision_threshold
        if not 0.05 <= threshold <= 0.95:
            raise HTTPException(status_code=400, detail="Threshold must be between 0.05 and 0.95")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > config.max_body_bytes:
                raise HTTPException(status_code=413, detail="Image is too large")
        if not body:
            raise HTTPException(status_code=400, detail="Image body is empty")
        try:
            result = await inference.detect(bytes(body), threshold)
        except InferenceNotReadyError as error:
            raise HTTPException(status_code=503, detail="Model is not ready") from error
        except InferenceBusyError as error:
            raise HTTPException(status_code=503, detail="Inference queue is full") from error
        except TimeoutError as error:
            raise HTTPException(status_code=504, detail="Inference timed out") from error
        return {"human": result.human, "confidence": round(result.confidence, 6)}

    @app.exception_handler(ValueError)
    async def invalid_value(_: Request, error: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    return app


app = create_app()
