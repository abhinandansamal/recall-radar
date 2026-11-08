"""Bootstrap test so CI has something to run before F01's real tests exist."""

import rr_core


def test_package_imports_and_has_version() -> None:
    assert rr_core.__version__ == "0.1.0"
