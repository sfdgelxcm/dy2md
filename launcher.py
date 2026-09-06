"""One-click launcher for the optional Douyin service and the desktop GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from service_manager import DouyinServiceManager


PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.yaml"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "未找到 config.yaml。请先复制 config.example.yaml 为 config.yaml 并完成配置。"
        )
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    if not isinstance(config, dict):
        raise ValueError("config.yaml 顶层必须是配置对象")
    return config


def show_error(message: str) -> None:
    try:
        from tkinter import Tk, messagebox

        root = Tk()
        root.withdraw()
        messagebox.showerror("Video to Markdown 启动失败", message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def run(*, service_only: bool = False) -> int:
    manager: DouyinServiceManager | None = None
    try:
        config = load_config()
        api_settings = config.get("douyin_api") or {}
        if not isinstance(api_settings, dict):
            raise ValueError("config.yaml 中的 douyin_api 必须是配置对象")

        manager = DouyinServiceManager(api_settings, config_dir=PROJECT_DIR)
        manager.ensure_running()

        if service_only:
            if not manager.is_running():
                raise RuntimeError(
                    "抖音解析服务未运行，且 douyin_api.auto_start.enabled 未启用"
                )
            print(f"Douyin API is ready: {manager.health_url}")
            return 0

        from gui_pro import main as run_gui

        run_gui()
        return 0
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        if service_only:
            print(message, file=sys.stderr)
        else:
            show_error(message)
        return 1
    finally:
        if manager is not None and not service_only:
            manager.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Douyin API when needed, then open the GUI")
    parser.add_argument(
        "--service-only",
        action="store_true",
        help="ensure the configured Douyin API is running, then exit",
    )
    args = parser.parse_args()
    raise SystemExit(run(service_only=bool(args.service_only)))


if __name__ == "__main__":
    main()
