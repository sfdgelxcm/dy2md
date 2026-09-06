"""Thin HTTP sidecar executed by the crawler project's Python environment.

The desktop application never imports crawler code. This process is launched
with Douyin_TikTok_Download_API's own virtual environment and exposes the small,
stable HTTP contract needed by video_to_markdown.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import traceback
from pathlib import Path
from typing import Any


# The launcher sets cwd to the crawler project. Python normally puts the
# sidecar's directory first on sys.path, so explicitly add the crawler root.
CRAWLER_PROJECT_DIR = Path.cwd().resolve()
sys.path.insert(0, str(CRAWLER_PROJECT_DIR))

try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Query
    from crawlers.douyin.web.web_crawler import DouyinWebCrawler
except ImportError as exc:
    raise RuntimeError(
        "crawler_sidecar.py must be executed with the "
        "Douyin_TikTok_Download_API virtual environment and project directory"
    ) from exc


app = FastAPI(
    title="Video to Markdown - Douyin Sidecar",
    version="1.0.0",
    docs_url="/docs",
)

MAX_ATTEMPTS = 5
RETRY_DELAY = 1.0


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/hybrid/video_data")
async def video_data(
    url: str = Query(..., description="Douyin video or short URL"),
    minimal: bool = Query(False),
) -> dict[str, Any]:
    del minimal  # The desktop app needs the complete payload for media URLs.
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            # Keep request state isolated. This avoids stale singleton state
            # in some versions of the upstream web API application.
            crawler = DouyinWebCrawler()
            aweme_id = await crawler.get_aweme_id(url)
            response = await crawler.fetch_one_video(aweme_id)
            data = response.get("aweme_detail") if isinstance(response, dict) else None
            if not isinstance(data, dict):
                raise ValueError("crawler response does not contain aweme_detail")
            return {
                "code": 200,
                "router": "/api/hybrid/video_data",
                "data": data,
            }
        except Exception as exc:
            last_error = exc
            print(
                f"Douyin parse attempt {attempt}/{MAX_ATTEMPTS} failed: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY * attempt)

    assert last_error is not None
    traceback.print_exception(last_error)
    raise HTTPException(
        status_code=502,
        detail={
            "code": 502,
            "message": f"{type(last_error).__name__}: {last_error}",
            "attempts": MAX_ATTEMPTS,
            "router": "/api/hybrid/video_data",
        },
    ) from last_error


def main() -> None:
    global MAX_ATTEMPTS, RETRY_DELAY
    parser = argparse.ArgumentParser(description="Run the Douyin crawler sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--retry-delay", type=float, default=1.0)
    args = parser.parse_args()
    MAX_ATTEMPTS = max(1, args.max_attempts)
    RETRY_DELAY = max(0.1, args.retry_delay)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
