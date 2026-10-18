import os

import pytest

from web import model

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "councils.json")


@pytest.fixture
def fixture_data(monkeypatch):
    """Six councils with known figures, instead of the real data."""
    monkeypatch.setattr(model, "DATA_FILE", FIXTURE)
    return model.load()
