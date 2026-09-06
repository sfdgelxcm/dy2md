"""Lifecycle management for an optional local Douyin API process.

The crawler remains a separate application with its own Python environment.
This module only starts that application's configured command and waits for its
HTTP endpoint; it never imports crawler code.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import httpx


class ServiceStartError(RuntimeError):
    """Raised when the configured local API service cannot be started."""


@dataclass(frozen=True)
class AutoStartSettings:
    enabled: bool
    project_dir: Path
    python_path: Path
    command: tuple[str, ...]
    startup_timeout: float
    poll_interval: float
    stop_on_exit: bool
    log_file: Path

    @classmethod
    def from_config(
        cls,
        settings: Mapping[str, Any],
        *,
        config_dir: Path,
    ) -> "AutoStartSettings":
        raw_project_dir = os.environ.get(
            "DOUYIN_API_PROJECT_DIR", str(settings.get("project_dir", ""))
        )
        project_dir = _resolve_path(raw_project_dir, config_dir)

        raw_python = str(settings.get("python", ".venv/Scripts/python.exe"))
        python_path = _resolve_path(raw_python, project_dir)

        command_value = settings.get("command")
        if command_value is None:
            command: Sequence[object] = (str(settings.get("entrypoint", "start.py")),)
        elif isinstance(command_value, (list, tuple)):
            command = command_value
        else:
            raise ValueError("douyin_api.auto_start.command 必须是 YAML 列表")

        raw_log_file = str(settings.get("log_file", "./logs/douyin_api_service.log"))
        log_file = _resolve_path(raw_log_file, config_dir)

        replacements = {
            "{app_dir}": str(config_dir),
            "{project_dir}": str(project_dir),
        }
        resolved_command: list[str] = []
        for item in command:
            value = str(item)
            for placeholder, replacement in replacements.items():
                value = value.replace(placeholder, replacement)
            if value.strip():
                resolved_command.append(value)

        return cls(
            enabled=bool(settings.get("enabled", False)),
            project_dir=project_dir,
            python_path=python_path,
            command=tuple(resolved_command),
            startup_timeout=max(1.0, float(settings.get("startup_timeout", 30))),
            poll_interval=max(0.1, float(settings.get("poll_interval", 0.5))),
            stop_on_exit=bool(settings.get("stop_on_exit", False)),
            log_file=log_file,
        )


def _resolve_path(value: str, base_dir: Path) -> Path:
    expanded = os.path.expandvars(os.path.expanduser(str(value or "").strip()))
    path = Path(expanded)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


class DouyinServiceManager:
    """Detect and optionally launch a separately installed Douyin API."""

    def __init__(
        self,
        api_settings: Mapping[str, Any],
        *,
        config_dir: Path,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = str(api_settings.get("base_url", "")).strip().rstrip("/")
        if not self.base_url:
            raise ValueError("请在 config.yaml 中配置 douyin_api.base_url")

        health_endpoint = str(
            api_settings.get("health_endpoint")
            or api_settings.get("endpoint")
            or "/docs"
        ).strip()
        self.health_endpoint = "/" + health_endpoint.lstrip("/")
        self.health_timeout = max(0.2, float(api_settings.get("health_timeout", 2)))
        self.trust_env = bool(api_settings.get("trust_env", False))
        self.transport = transport

        auto_start = api_settings.get("auto_start") or {}
        if not isinstance(auto_start, Mapping):
            raise ValueError("douyin_api.auto_start 必须是配置对象")
        self.auto_start = AutoStartSettings.from_config(
            auto_start,
            config_dir=config_dir,
        )
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.started_by_launcher = False

    @property
    def health_url(self) -> str:
        return f"{self.base_url}{self.health_endpoint}"

    def is_running(self) -> bool:
        """Return whether the configured HTTP service responds."""
        try:
            with httpx.Client(
                timeout=self.health_timeout,
                follow_redirects=True,
                trust_env=self.trust_env,
                transport=self.transport,
            ) as client:
                response = client.get(self.health_url)
            return 200 <= response.status_code < 400
        except httpx.RequestError:
            return False

    def ensure_running(self) -> bool:
        """Start the local service when needed.

        Returns True only when this manager started a new process. If automatic
        startup is disabled, an unavailable service does not block local-file
        workflows and the GUI is still allowed to open.
        """
        if self.is_running():
            return False
        if not self.auto_start.enabled:
            return False

        self._validate_startup_files()
        self.auto_start.log_file.parent.mkdir(parents=True, exist_ok=True)
        command = [str(self.auto_start.python_path), *self.auto_start.command]
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONUTF8"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"

        creationflags = 0
        popen_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        with self.auto_start.log_file.open("ab") as log:
            self.process = subprocess.Popen(
                command,
                cwd=str(self.auto_start.project_dir),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=environment,
                creationflags=creationflags,
                **popen_kwargs,
            )
        self.started_by_launcher = True

        deadline = time.monotonic() + self.auto_start.startup_timeout
        while time.monotonic() < deadline:
            if self.is_running():
                return True
            if self.process.poll() is not None:
                tail = self._read_log_tail()
                raise ServiceStartError(
                    "抖音解析服务启动后立即退出"
                    + (f"：\n{tail}" if tail else "，请查看服务日志")
                )
            time.sleep(self.auto_start.poll_interval)

        self.stop(force=True)
        raise ServiceStartError(
            f"等待抖音解析服务就绪超时（{self.auto_start.startup_timeout:g} 秒）。"
            f"日志：{self.auto_start.log_file}"
        )

    def stop(self, *, force: bool = False) -> None:
        """Stop only a process started by this manager."""
        process = self.process
        if not self.started_by_launcher or process is None or process.poll() is not None:
            return
        if not force and not self.auto_start.stop_on_exit:
            return

        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _validate_startup_files(self) -> None:
        settings = self.auto_start
        if not settings.project_dir.is_dir():
            raise ServiceStartError(
                f"抖音解析项目目录不存在：{settings.project_dir}\n"
                "请修改 config.yaml 中的 douyin_api.auto_start.project_dir。"
            )
        if not settings.python_path.is_file():
            raise ServiceStartError(
                f"抖音解析服务的 Python 不存在：{settings.python_path}\n"
                "请先为爬虫项目创建独立虚拟环境并安装依赖。"
            )
        if not settings.command:
            raise ServiceStartError("douyin_api.auto_start.command 不能为空")

        first_arg = Path(settings.command[0])
        if first_arg.suffix.lower() == ".py":
            entrypoint = first_arg if first_arg.is_absolute() else settings.project_dir / first_arg
            if not entrypoint.is_file():
                raise ServiceStartError(f"抖音解析服务入口不存在：{entrypoint}")

    def _read_log_tail(self, max_chars: int = 2000) -> str:
        try:
            text = self.auto_start.log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return text[-max_chars:].strip()
