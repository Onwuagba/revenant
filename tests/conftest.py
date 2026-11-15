"""Shared pytest configuration: register the ``pbt`` marker and Hypothesis profiles.

Profiles (from steering testing.md / docs/TESTING.md):
  - dev:  50 examples, fast, used by the on-save hook
  - ci:   200 examples, derandomised seed printed
  - deep: nightly/manual, higher example count

The marker is registered programmatically so no separate ini file is needed.
"""

from __future__ import annotations

import pytest
from hypothesis import settings, HealthCheck


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "pbt: property-based tests using Hypothesis")
    config.addinivalue_line("markers", "integration: integration tests using in-process mocks")
    config.addinivalue_line("markers", "e2e: end-to-end tests")


# ---------------------------------------------------------------------------
# Hypothesis profiles
# ---------------------------------------------------------------------------
settings.register_profile(
    "dev",
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "ci",
    max_examples=200,
    derandomize=True,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
    print_blob=True,
)
settings.register_profile(
    "deep",
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# Load the profile from --hypothesis-profile=<name>, default to dev.
settings.load_profile("dev")
