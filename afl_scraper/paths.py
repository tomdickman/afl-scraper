"""Central application artifact paths.

The data lake remains relative to the working directory by default for backwards
compatibility. Deployments and tests can set ``AFL_SCRAPER_DATA_DIR`` explicitly.
"""

import os
from pathlib import Path


def data_root() -> Path:
    return Path(os.environ.get("AFL_SCRAPER_DATA_DIR", "data"))


def data_path(*parts: str | int) -> Path:
    return data_root().joinpath(*(str(part) for part in parts))


__all__ = ["data_path", "data_root"]
