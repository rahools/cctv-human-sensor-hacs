from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from .settings import Settings


@dataclass(frozen=True, slots=True)
class Detection:
    human: bool
    confidence: float
    queue_ms: float = 0.0
    inference_ms: float = 0.0


class Engine(Protocol):
    ready: bool

    async def start(self) -> None: ...

    async def close(self) -> None: ...

    def detect(self, image: bytes, threshold: float) -> Awaitable[Detection]: ...


class InferenceBusyError(RuntimeError):
    pass


class InferenceNotReadyError(RuntimeError):
    pass


class HunchEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ready = False
        self._queue: asyncio.Queue[tuple[bytes, float, float, asyncio.Future[Detection]] | None] = asyncio.Queue(
            maxsize=settings.queue_size
        )
        self._worker: asyncio.Task[None] | None = None
        self._eyes: Any = None
        self._detector: Any = None

    async def start(self) -> None:
        await asyncio.to_thread(self._load)
        self.ready = True
        self._worker = asyncio.create_task(self._run(), name="hunch-inference")

    def _load(self) -> None:
        from hunch.live import Detector, Eyes

        self._eyes = Eyes(tokens=self.settings.image_tokens)
        self._detector = Detector(
            self._eyes,
            yes=[
                "a surveillance image containing one or more people",
                "a CCTV photograph of a person",
                "a person visible in a security camera image",
            ],
            no=[
                "an empty surveillance scene with no people",
                "a CCTV photograph showing objects but no people",
                "a security camera image of an empty area",
            ],
        )
        self._eyes.warm()

    async def close(self) -> None:
        self.ready = False
        if self._worker is None:
            return
        await self._queue.put(None)
        await self._worker
        self._worker = None

    def detect(self, image: bytes, threshold: float) -> Awaitable[Detection]:
        return self._enqueue(image, threshold)

    async def _enqueue(self, image: bytes, threshold: float) -> Detection:
        if not self.ready:
            raise InferenceNotReadyError
        future = asyncio.get_running_loop().create_future()
        try:
            self._queue.put_nowait((image, threshold, time.monotonic(), future))
        except asyncio.QueueFull as error:
            raise InferenceBusyError from error
        try:
            return await asyncio.wait_for(future, timeout=self.settings.request_timeout)
        except TimeoutError:
            future.cancel()
            raise

    async def _run(self) -> None:
        while (item := await self._queue.get()) is not None:
            image, threshold, queued_at, future = item
            if future.cancelled():
                continue
            queue_ms = (time.monotonic() - queued_at) * 1000
            inference_started = time.monotonic()
            try:
                result = await asyncio.to_thread(self._infer, image, threshold)
            except Exception as error:
                if not future.done():
                    future.set_exception(error)
            else:
                result = replace(
                    result,
                    queue_ms=queue_ms,
                    inference_ms=(time.monotonic() - inference_started) * 1000,
                )
                if not future.done():
                    future.set_result(result)

    def _infer(self, image: bytes, threshold: float) -> Detection:
        if self._eyes is None or self._detector is None:
            raise InferenceNotReadyError
        embedding, _ = self._eyes.see(image)
        answer = self._detector.ask(embedding)
        confidence = answer["p"]
        if confidence is None:
            raise InferenceNotReadyError
        return Detection(human=confidence >= threshold, confidence=confidence)


EngineFactory = Callable[[Settings], Engine]
