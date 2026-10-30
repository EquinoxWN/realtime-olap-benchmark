import realtime_olap_benchmark


def test_version() -> None:
    """The package exposes its version."""
    assert realtime_olap_benchmark.__version__ == "0.1.0"
