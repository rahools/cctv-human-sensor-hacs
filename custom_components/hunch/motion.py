from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class MotionResult:
    motion: bool
    changed_area: float
    scene_change: bool


class MotionDetector:
    def __init__(self, pixel_threshold: int, area_threshold: float, trigger_frames: int) -> None:
        self.pixel_threshold = pixel_threshold
        self.area_threshold = area_threshold
        self.trigger_frames = trigger_frames
        self._previous: np.ndarray | None = None
        self._streak = 0

    def reset(self) -> None:
        self._previous = None
        self._streak = 0

    def compare(self, current: np.ndarray) -> MotionResult:
        previous = self._previous
        self._previous = current.copy()
        if previous is None or previous.shape != current.shape:
            self._streak = 0
            return MotionResult(False, 0.0, False)

        signed = current - previous
        compensation = float(np.median(signed))
        difference = np.abs(signed - compensation)
        changed = difference >= self.pixel_threshold
        changed_area = float(np.count_nonzero(changed)) / changed.size
        raw_difference = np.abs(signed)
        raw_changed_area = float(np.count_nonzero(raw_difference >= self.pixel_threshold)) / signed.size
        scene_change = raw_changed_area > 0.95 and abs(float(np.mean(signed))) > self.pixel_threshold

        if changed_area >= self.area_threshold and not scene_change:
            self._streak += 1
        else:
            self._streak = 0
        return MotionResult(self._streak >= self.trigger_frames, changed_area, scene_change)
