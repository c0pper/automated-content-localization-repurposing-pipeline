from __future__ import annotations

import pytest

from app.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        data_dir=tmp_path / "data",
        public_base_url="http://testserver/assets",
        run_worker=False,
        retention_sweep_seconds=0,
        worker_poll_seconds=0.01,
    )
