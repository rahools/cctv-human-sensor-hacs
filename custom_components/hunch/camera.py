from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .api import HunchClient, HunchConnectionError, SnapshotClient
from .const import (
    CONF_AREA_THRESHOLD,
    CONF_CLEAR_DELAY,
    CONF_DETECTION_INTERVAL,
    CONF_MOTION_ENABLED,
    CONF_MOTION_END_DELAY,
    CONF_PIXEL_THRESHOLD,
    CONF_POLL_INTERVAL,
    CONF_THRESHOLD,
    CONF_TRIGGER_FRAMES,
    CONF_ZONE,
    DEFAULT_AREA_THRESHOLD,
    DEFAULT_CLEAR_DELAY,
    DEFAULT_DETECTION_INTERVAL,
    DEFAULT_MOTION_END_DELAY,
    DEFAULT_PIXEL_THRESHOLD,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_THRESHOLD,
    DEFAULT_TRIGGER_FRAMES,
)
from .image import InvalidImageError, process_frame
from .motion import MotionDetector


class CameraRuntime:
    def __init__(
        self,
        hass: HomeAssistant,
        subentry_id: str,
        config: dict[str, Any],
        snapshots: SnapshotClient,
        detector: HunchClient,
    ) -> None:
        self.hass = hass
        self.subentry_id = subentry_id
        self.config = dict(config)
        self.snapshots = snapshots
        self.detector = detector
        self.human: bool | None = None
        self.motion = False
        self.available = True
        self.confidence: float | None = None
        self.last_checked: float | None = None
        self.last_detected: float | None = None
        self.last_error: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._listeners: list[Callable[[], None]] = []
        self._motion = MotionDetector(
            int(self.config.get(CONF_PIXEL_THRESHOLD, DEFAULT_PIXEL_THRESHOLD)),
            float(self.config.get(CONF_AREA_THRESHOLD, DEFAULT_AREA_THRESHOLD)),
            int(self.config.get(CONF_TRIGGER_FRAMES, DEFAULT_TRIGGER_FRAMES)),
        )
        self._last_motion = 0.0
        self._last_detection_attempt = 0.0
        self._failures = 0

    @callback
    def async_listen(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    def _state(self) -> tuple[Any, ...]:
        return (
            self.human,
            self.motion,
            self.available,
            self.confidence,
            self.last_checked,
            self.last_detected,
            self.last_error,
        )

    async def async_start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"hunch-camera-{self.subentry_id}")

    async def async_stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def apply_zone(self, zone: dict[str, float] | None) -> None:
        self.config[CONF_ZONE] = zone
        self._motion.reset()
        self.motion = False
        self.human = None
        self.confidence = None
        self._notify()

    async def fetch_preview(self) -> bytes:
        return (await self.snapshots.fetch()).data

    async def _run(self) -> None:
        while True:
            started = time.monotonic()
            await self._tick()
            interval = float(self.config.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
            delay = interval if self._failures == 0 else min(30.0, interval * 2 ** min(self._failures, 5))
            await asyncio.sleep(max(0.1, delay - (time.monotonic() - started)))

    async def _tick(self) -> None:
        before = self._state()
        try:
            snapshot = await self.snapshots.fetch()
            frame = await self.hass.async_add_executor_job(process_frame, snapshot.data, self.config)
        except (HunchConnectionError, InvalidImageError, OSError, ValueError) as error:
            self._record_failure(error)
            if before != self._state():
                self._notify()
            return

        now = time.monotonic()
        should_detect = True
        if self.config.get(CONF_MOTION_ENABLED, True):
            result = self._motion.compare(frame.analysis)
            if result.motion:
                self._last_motion = now
                self.motion = True
            elif now - self._last_motion >= float(self.config.get(CONF_MOTION_END_DELAY, DEFAULT_MOTION_END_DELAY)):
                self.motion = False
            detection_interval = float(self.config.get(CONF_DETECTION_INTERVAL, DEFAULT_DETECTION_INTERVAL))
            should_detect = self.motion and now - self._last_detection_attempt >= detection_interval
            if not self.motion:
                self._clear_if_stale(now)

        if should_detect:
            self._last_detection_attempt = now
            try:
                human, confidence = await self.detector.detect(
                    frame.image, float(self.config.get(CONF_THRESHOLD, DEFAULT_THRESHOLD))
                )
            except HunchConnectionError as error:
                self._record_failure(error)
            else:
                self._failures = 0
                self.available = True
                self.last_error = None
                self._record_detection(human, confidence)
        else:
            self._failures = 0
            self.available = True
            self.last_error = None
        if before != self._state():
            self._notify()

    def _record_detection(self, human: bool, confidence: float) -> None:
        now = time.monotonic()
        self.last_checked = time.time()
        self.confidence = confidence
        if human:
            self.last_detected = self.last_checked
            self.human = True
        elif self.human is None or now - self._positive_monotonic() >= float(
            self.config.get(CONF_CLEAR_DELAY, DEFAULT_CLEAR_DELAY)
        ):
            self.human = False

    def _clear_if_stale(self, now: float) -> None:
        if self.human and now - self._positive_monotonic() >= float(
            self.config.get(CONF_CLEAR_DELAY, DEFAULT_CLEAR_DELAY)
        ):
            self.human = False

    def _positive_monotonic(self) -> float:
        if self.last_detected is None:
            return 0.0
        return time.monotonic() - max(0.0, time.time() - self.last_detected)

    def _record_failure(self, error: Exception) -> None:
        self._failures += 1
        self.last_error = type(error).__name__
        if self._failures >= 3:
            self.available = False
