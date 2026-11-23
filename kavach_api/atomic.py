"""Atomic filesystem helpers with retry on Windows file lock collisions."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from typing import Union

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]


def replace_with_retry(
    src: PathLike,
    dst: PathLike,
    attempts: int = 20,
    delay: float = 0.01,
) -> None:
    """Atomically replace dst with src, retrying on transient Windows PermissionError.

    Looks up os.replace dynamically at call time so tests and monkeypatches work.
    """
    last_err: PermissionError | None = None
    dst_name = Path(dst).name
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError as e:
            last_err = e
            logger.debug(
                "Retry %d/%d replacing %s on PermissionError",
                i + 1,
                attempts,
                dst_name,
            )
            if i < attempts - 1 and delay > 0:
                time.sleep(delay)
    if last_err is not None:
        raise last_err
