"""Atomic writes and environment validation added in the 2026-11-01 quality pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from realtime_olap_benchmark.engines.base import EngineError, port_from_env
from realtime_olap_benchmark.fsutil import write_text_atomic


def test_write_text_atomic_replaces_and_leaves_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    target.write_text("old", encoding="utf-8")
    write_text_atomic(target, "new")
    write_text_atomic(target, "new")  # same write twice: one file, same content
    assert target.read_text(encoding="utf-8") == "new"
    assert [p.name for p in tmp_path.iterdir()] == ["result.json"]


@pytest.mark.parametrize("raw", ["abc", "0", "65536", "-1", ""])
def test_port_from_env_rejects_bad_ports(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("DORIS_PORT", raw)
    with pytest.raises(EngineError, match="DORIS_PORT"):
        port_from_env("DORIS_PORT", "9030")


def test_port_from_env_default_and_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DORIS_PORT", raising=False)
    assert port_from_env("DORIS_PORT", "9030") == 9030
    monkeypatch.setenv("DORIS_PORT", "65535")
    assert port_from_env("DORIS_PORT", "9030") == 65535
