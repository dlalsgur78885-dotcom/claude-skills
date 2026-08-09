"""No-reference IQA via pyiqa: BRISQUE + NIQE.

Both metrics are lower-is-better. We crudely normalize to 0~100, average,
and invert so the returned score is higher = better. Range: 0~100.

Models lazy-load on first call (~3-5s init). Subsequent calls are CPU-fast.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _models():
    import pyiqa

    return {
        "brisque": pyiqa.create_metric("brisque", as_loss=False),
        "niqe": pyiqa.create_metric("niqe", as_loss=False),
    }


def assess_quality(image_path: str | Path) -> float:
    """Return 0~100 quality score (higher = better). 0.0 on error."""
    try:
        m = _models()
        path = str(image_path)
        brisque = float(m["brisque"](path).item())  # 0~100, lower better
        niqe = float(m["niqe"](path).item())        # ~3-15, lower better

        b = max(0.0, min(100.0, brisque))
        n = max(0.0, min(100.0, niqe * 10.0))
        badness = (b + n) / 2
        return round(100.0 - badness, 2)
    except Exception as e:
        logger.warning(f"[quality] assess failed for {image_path}: {e}")
        return 0.0
