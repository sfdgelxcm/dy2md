"""Download media using an independent Douyin parsing HTTP service."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple, TypeGuard

import httpx
import yaml

from douyin_api_client import DouyinApiClient
from url_utils import extract_http_url


def _load_config() -> dict[str, Any]:
    config_path = Path(__file__).resolve().with_name("config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(
            "未找到 config.yaml，请先复制 config.example.yaml 为 config.yaml 并完成配置"
        )
    with config_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


class DouyinDownloader:
    """Resolve video metadata through HTTP, then download the media stream."""

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        api_client: Optional[DouyinApiClient] = None,
    ) -> None:
        app_config = dict(config or _load_config())
        api_settings = app_config.get("douyin_api") or {}
        download_settings = app_config.get("download") or {}

        if not isinstance(api_settings, Mapping):
            raise ValueError("config.yaml 中的 douyin_api 必须是配置对象")
        if not isinstance(download_settings, Mapping):
            raise ValueError("config.yaml 中的 download 必须是配置对象")

        self.api_client = api_client or DouyinApiClient.from_config(api_settings)
        self.temp_dir = str(download_settings.get("temp_dir", "./temp"))
        self.download_timeout = float(download_settings.get("timeout", 120))
        self.max_retries = max(1, int(download_settings.get("max_retries", 3)))
        os.makedirs(self.temp_dir, exist_ok=True)

        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }

    @staticmethod
    def _is_http_url(value: object) -> TypeGuard[str]:
        return isinstance(value, str) and value.startswith(("http://", "https://"))

    def _collect_url_list(self, value: object) -> list[str]:
        if self._is_http_url(value):
            return [value]
        if not isinstance(value, Mapping):
            return []

        urls: list[str] = []
        url_list = value.get("url_list")
        if isinstance(url_list, list):
            urls.extend(item for item in url_list if self._is_http_url(item))

        url = value.get("url")
        if self._is_http_url(url):
            urls.append(url)
        return urls

    def _collect_urls_by_key_prefix(
        self, value: object, prefixes: tuple[str, ...]
    ) -> list[str]:
        if not isinstance(value, Mapping):
            return []
        urls: list[str] = []
        for key, item in value.items():
            if any(str(key).startswith(prefix) for prefix in prefixes):
                urls.extend(self._collect_url_list(item))
        return urls

    @staticmethod
    def _deduplicate(urls: list[str]) -> list[str]:
        return list(dict.fromkeys(urls))

    @staticmethod
    def _author_name(author: object) -> str:
        if isinstance(author, str):
            return author
        if isinstance(author, Mapping):
            for key in ("nickname", "name", "unique_id"):
                value = author.get(key)
                if value:
                    return str(value)
        return ""

    async def get_video_info(self, url: str) -> Dict[str, Any]:
        """Resolve a share URL into the stable metadata shape used by the app."""
        clean_url = extract_http_url(url)
        data = await self.api_client.fetch_video_data(clean_url, minimal=False)

        music = data.get("music") if isinstance(data.get("music"), Mapping) else {}
        video = data.get("video") if isinstance(data.get("video"), Mapping) else {}
        video_data = (
            data.get("video_data") if isinstance(data.get("video_data"), Mapping) else {}
        )

        audio_urls: list[str] = []
        audio_urls.extend(self._collect_url_list(music.get("play_url")))
        audio_urls.extend(self._collect_urls_by_key_prefix(music, ("play_url",)))
        audio_urls.extend(self._collect_url_list(video_data.get("audio_url")))

        video_urls: list[str] = []
        for key in ("play_addr", "play_addr_h264", "play_addr_bytevc1", "download_addr"):
            video_urls.extend(self._collect_url_list(video.get(key)))
        video_urls.extend(
            self._collect_urls_by_key_prefix(video, ("play_addr", "download_addr"))
        )
        for key in (
            "nwm_video_url_HQ",
            "nwm_video_url",
            "wm_video_url_HQ",
            "wm_video_url",
        ):
            video_urls.extend(self._collect_url_list(video_data.get(key)))

        audio_urls = self._deduplicate(audio_urls)
        video_urls = self._deduplicate(video_urls)

        aweme_id = data.get("aweme_id") or data.get("video_id") or data.get("id")
        description = data.get("desc") or data.get("title") or ""

        return {
            "aweme_id": aweme_id,
            "desc": str(description),
            "author": self._author_name(data.get("author")),
            "audio_url": audio_urls[0] if audio_urls else None,
            "audio_urls": audio_urls,
            "video_url": video_urls[0] if video_urls else None,
            "video_urls": video_urls,
            "music_title": str(music.get("title") or ""),
            "duration": data.get("duration", 0),
        }

    async def download_audio(
        self, url: str, output_path: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Download audio when available, otherwise download video for ASR."""
        info = await self.get_video_info(url)
        audio_url = info.get("audio_url")
        video_url = info.get("video_url")

        if not self._is_http_url(audio_url) and not self._is_http_url(video_url):
            aweme_id = info.get("aweme_id")
            raise ValueError(
                "解析结果中没有可用的音频或视频地址，请检查解析服务版本及 Cookie"
                + (f"，aweme_id={aweme_id}" if aweme_id else "")
            )

        if output_path is None:
            aweme_id = str(info.get("aweme_id") or "douyin")
            suffix = ".m4a" if self._is_http_url(audio_url) else ".mp4"
            output_path = os.path.join(self.temp_dir, f"{aweme_id}{suffix}")

        download_url = audio_url if self._is_http_url(audio_url) else video_url
        assert isinstance(download_url, str)

        transport = httpx.AsyncHTTPTransport(retries=5)
        timeout = httpx.Timeout(self.download_timeout)
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=5)

        async with httpx.AsyncClient(
            headers=self._headers,
            timeout=timeout,
            limits=limits,
            transport=transport,
            follow_redirects=True,
        ) as client:
            for attempt in range(self.max_retries):
                try:
                    async with client.stream("GET", download_url) as response:
                        response.raise_for_status()
                        with open(output_path, "wb") as file:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                file.write(chunk)
                    break
                except (httpx.ReadError, httpx.ConnectError, httpx.TimeoutException):
                    if attempt >= self.max_retries - 1:
                        raise
                    await asyncio.sleep(2 * (attempt + 1))

        return output_path, info

    async def close(self) -> None:
        """Compatibility hook; clients are scoped to individual requests."""


async def main() -> None:
    """Manual downloader smoke test."""
    downloader = DouyinDownloader()
    url = input("请输入抖音视频或分享链接：").strip()
    info = await downloader.get_video_info(url)
    print(f"标题: {info['desc']}")
    print(f"作者: {info['author']}")
    path, _ = await downloader.download_audio(url)
    print(f"已保存到: {path}")


if __name__ == "__main__":
    asyncio.run(main())
