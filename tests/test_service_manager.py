from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from service_manager import AutoStartSettings, DouyinServiceManager


class AutoStartSettingsTests(unittest.TestCase):
    def test_resolves_crawler_python_relative_to_crawler_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            settings = AutoStartSettings.from_config(
                {
                    "enabled": True,
                    "project_dir": "../crawler",
                    "python": ".venv/Scripts/python.exe",
                    "command": ["{app_dir}/crawler_sidecar.py", "--port", "8000"],
                },
                config_dir=config_dir,
            )

        self.assertEqual(settings.project_dir, (config_dir / "../crawler").resolve())
        self.assertEqual(
            settings.python_path,
            (config_dir / "../crawler/.venv/Scripts/python.exe").resolve(),
        )
        self.assertEqual(Path(settings.command[0]), (config_dir / "crawler_sidecar.py").resolve())
        self.assertEqual(settings.command[-2:], ("--port", "8000"))


class DouyinServiceManagerTests(unittest.TestCase):
    def test_health_endpoint_must_return_success(self) -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(422, json={"detail": "missing url"})
        )
        manager = DouyinServiceManager(
            {
                "base_url": "http://douyin-api.local",
                "health_endpoint": "/api/hybrid/video_data",
                "auto_start": {"enabled": False},
            },
            config_dir=PROJECT_ROOT,
            transport=transport,
        )
        self.assertFalse(manager.is_running())

    def test_disabled_auto_start_does_not_spawn_process(self) -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(503, json={"detail": "starting"})
        )
        manager = DouyinServiceManager(
            {
                "base_url": "http://douyin-api.local",
                "health_endpoint": "/docs",
                "auto_start": {"enabled": False},
            },
            config_dir=PROJECT_ROOT,
            transport=transport,
        )
        self.assertFalse(manager.ensure_running())
        self.assertIsNone(manager.process)


if __name__ == "__main__":
    unittest.main()
