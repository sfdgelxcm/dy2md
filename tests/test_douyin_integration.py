from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from douyin_api_client import DouyinApiClient, DouyinApiResponseError
from downloader import DouyinDownloader


class FakeDouyinApiClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, bool]] = []

    async def fetch_video_data(self, url: str, *, minimal: bool = False) -> dict[str, Any]:
        self.calls.append((url, minimal))
        return self.payload


class DouyinApiClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_unwraps_standard_api_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/hybrid/video_data")
            self.assertEqual(request.url.params["minimal"], "false")
            return httpx.Response(
                200,
                json={"code": 200, "router": request.url.path, "data": {"aweme_id": "123"}},
            )

        client = DouyinApiClient(
            "http://douyin-api.local",
            transport=httpx.MockTransport(handler),
        )
        data = await client.fetch_video_data("https://www.douyin.com/video/123")
        self.assertEqual(data["aweme_id"], "123")

    async def test_rejects_non_json_response(self) -> None:
        client = DouyinApiClient(
            "http://douyin-api.local",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, content=b"not-json")
            ),
        )
        with self.assertRaises(DouyinApiResponseError):
            await client.fetch_video_data("https://www.douyin.com/video/123")

    async def test_extracts_concise_fastapi_error(self) -> None:
        client = DouyinApiClient(
            "http://douyin-api.local",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    502,
                    json={
                        "detail": {
                            "message": "APIResponseError: HTTP status 403",
                            "attempts": 5,
                        }
                    },
                )
            ),
        )
        with self.assertRaisesRegex(DouyinApiResponseError, "已尝试 5 次"):
            await client.fetch_video_data("https://www.douyin.com/video/123")


class DouyinDownloaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_crawler_payload_without_importing_crawler_code(self) -> None:
        payload = {
            "aweme_id": "123",
            "desc": "demo",
            "author": {"nickname": "author"},
            "duration": 1000,
            "music": {
                "title": "track",
                "play_url": {"url_list": ["https://cdn.example/audio.m4a"]},
            },
            "video": {
                "play_addr": {"url_list": ["https://cdn.example/video.mp4"]}
            },
        }
        fake_client = FakeDouyinApiClient(payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            downloader = DouyinDownloader(
                {"douyin_api": {}, "download": {"temp_dir": temp_dir}},
                api_client=fake_client,  # type: ignore[arg-type]
            )
            result = await downloader.get_video_info(
                "分享文本 https://www.douyin.com/video/123 复制打开"
            )

        self.assertEqual(result["aweme_id"], "123")
        self.assertEqual(result["author"], "author")
        self.assertEqual(result["audio_url"], "https://cdn.example/audio.m4a")
        self.assertEqual(result["video_url"], "https://cdn.example/video.mp4")
        self.assertEqual(
            fake_client.calls,
            [("https://www.douyin.com/video/123", False)],
        )


if __name__ == "__main__":
    unittest.main()
