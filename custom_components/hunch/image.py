from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, UnidentifiedImageError

from .const import CONF_ZONE


class InvalidImageError(ValueError):
    pass


@dataclass(slots=True)
class ProcessedFrame:
    image: bytes
    analysis: np.ndarray
    width: int
    height: int


def image_dimensions(data: bytes) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise InvalidImageError("Only JPEG and PNG images are supported")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            return image.size
    except (UnidentifiedImageError, OSError) as error:
        raise InvalidImageError("The response is not a valid JPEG or PNG") from error


def process_frame(data: bytes, config: dict[str, Any]) -> ProcessedFrame:
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            image = source.convert("RGB")
    except (UnidentifiedImageError, OSError) as error:
        raise InvalidImageError from error

    zone = config.get(CONF_ZONE)
    cropped = image
    if zone:
        left = max(0, min(image.width - 1, round(float(zone["x"]) * image.width)))
        top = max(0, min(image.height - 1, round(float(zone["y"]) * image.height)))
        right = max(left + 1, min(image.width, round((float(zone["x"]) + float(zone["width"])) * image.width)))
        bottom = max(top + 1, min(image.height, round((float(zone["y"]) + float(zone["height"])) * image.height)))
        cropped = image.crop((left, top, right, bottom))

    output = io.BytesIO()
    if zone:
        cropped.save(output, format="JPEG", quality=90)
        image_bytes = output.getvalue()
    else:
        image_bytes = data

    analysis_width = min(256, cropped.width)
    analysis_height = max(1, round(cropped.height * analysis_width / cropped.width))
    analysis_image = cropped.convert("L").resize((analysis_width, analysis_height), Image.Resampling.BILINEAR)
    analysis_image = analysis_image.filter(ImageFilter.GaussianBlur(radius=1.0))
    analysis = np.asarray(analysis_image, dtype=np.float32)
    return ProcessedFrame(image_bytes, analysis, image.width, image.height)
