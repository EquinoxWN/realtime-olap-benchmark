"""Small file helpers shared by the generator, the result writer and the CLI."""

from __future__ import annotations

import os
from pathlib import Path


def write_text_atomic(path: Path, text: str) -> None:
    """Write to a sibling temp file, then rename it over path: readers see the old or the new file."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
