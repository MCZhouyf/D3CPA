from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class ImageEncoder(Protocol):
    def encode_image(self, image: Any) -> np.ndarray:
        ...


@runtime_checkable
class TextEncoder(Protocol):
    def encode_text(self, text: str) -> np.ndarray:
        ...


def as_float_vector(value: Any) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float32).reshape(-1)
    if vector.size == 0:
        raise ValueError("Embedding vectors cannot be empty")
    if not np.isfinite(vector).all():
        raise ValueError("Embedding vectors must be finite")
    return vector


@dataclass
class CallableImageEncoder:
    function: Callable[[Any], Any]

    def encode_image(self, image: Any) -> np.ndarray:
        return as_float_vector(self.function(image))


@dataclass
class CallableTextEncoder:
    function: Callable[[str], Any]

    def encode_text(self, text: str) -> np.ndarray:
        return as_float_vector(self.function(text))


class RGBHistogramEncoder:
    """Deterministic development fallback, not a paper-grade MineCLIP replacement."""

    def __init__(self, bins: int = 16):
        if bins <= 1:
            raise ValueError("bins must be greater than one")
        self.bins = bins

    def encode_image(self, image: Any) -> np.ndarray:
        array = np.asarray(image)
        if array.ndim != 3 or array.shape[-1] not in {3, 4}:
            raise ValueError("Expected an HxWx3 or HxWx4 image")
        array = array[..., :3].astype(np.float32)
        features = []
        for channel in range(3):
            histogram, _ = np.histogram(
                array[..., channel], bins=self.bins, range=(0.0, 255.0)
            )
            features.append(histogram.astype(np.float32))
        vector = np.concatenate(features)
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector


class HashingTextEncoder:
    """Stable bag-of-token hashing for tests and offline smoke runs."""

    TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)

    def __init__(self, dimensions: int = 256):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def encode_text(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimensions, dtype=np.float32)
        for token in self.TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "big") % self.dimensions
            vector[bucket] += 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector
