"""HTTP client for an independently deployed Douyin parsing service.

This module is the integration boundary between this project and
Douyin_TikTok_Download_API. It intentionally does not import crawler code.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx


class DouyinApiError(RuntimeError):
    """Base error raised by the Douyin parsing service adapter."""


class DouyinApiConnectionError(DouyinApiError):
    """Raised when the configured parsing service cannot be reached."""


class DouyinApiResponseError(DouyinApiError):
    """Raised when the parsing service returns an invalid response."""


class DouyinApiClient:
    """Small async client for the parsing service's HTTP API."""

    def __init__(
        self,
        base_url: str,
        endpoint: str = "/api/hybrid/video_data",
        timeout: float = 60,
        *,
        trust_env: bool = False,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        base_url = str(base_url or "").strip().rstrip("/")
        endpoint = str(endpoint or "").strip()

        if not base_url:
            raise ValueError("请在 config.yaml 中配置 douyin_api.base_url")
        if not endpoint:
            raise ValueError("请在 config.yaml 中配置 douyin_api.endpoint")

        self.base_url = base_url
        self.endpoint = "/" + endpoint.lstrip("/")
        self.timeout = float(timeout)
        self.trust_env = bool(trust_env)
        self.transport = transport

    @classmethod
    def from_config(
        cls,
        settings: Mapping[str, Any],
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> "DouyinApiClient":
        return cls(
            base_url=str(settings.get("base_url", "")),
            endpoint=str(settings.get("endpoint", "/api/hybrid/video_data")),
            timeout=float(settings.get("timeout", 60)),
            trust_env=bool(settings.get("trust_env", False)),
            transport=transport,
        )

    @property
    def request_url(self) -> str:
        return f"{self.base_url}{self.endpoint}"

    async def fetch_video_data(self, url: str, *, minimal: bool = False) -> dict[str, Any]:
        """Parse one video URL and return the unwrapped service payload."""
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                trust_env=self.trust_env,
                transport=self.transport,
            ) as client:
                response = await client.get(
                    self.request_url,
                    params={"url": url, "minimal": str(bool(minimal)).lower()},
                )
                response.raise_for_status()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise DouyinApiConnectionError(
                "无法连接抖音解析服务。请确认服务已启动，并检查 "
                "config.yaml 中的 douyin_api.base_url 与 endpoint。"
            ) from exc
        except httpx.TimeoutException as exc:
            raise DouyinApiConnectionError(
                f"抖音解析服务请求超时（{self.timeout:g} 秒）。"
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = self._http_error_detail(exc.response)
            suffix = f"：{detail}" if detail else ""
            raise DouyinApiResponseError(
                f"抖音解析服务返回 HTTP {exc.response.status_code}{suffix}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise DouyinApiResponseError("抖音解析服务返回的不是有效 JSON") from exc

        if not isinstance(payload, dict):
            raise DouyinApiResponseError("抖音解析服务返回的 JSON 顶层必须是对象")

        # Douyin_TikTok_Download_API uses {code, router, data}. Accepting a
        # raw object as well makes the adapter compatible with thin proxies.
        if "code" in payload:
            code = payload.get("code")
            if code not in (0, 200, "0", "200", None):
                raise DouyinApiResponseError(f"抖音解析服务返回业务错误码：{code}")

        data = payload.get("data", payload)
        if not isinstance(data, dict):
            raise DouyinApiResponseError("抖音解析服务响应中缺少有效的 data 对象")

        # Some deployments add one more conventional wrapper.
        if isinstance(data.get("aweme_detail"), dict):
            data = data["aweme_detail"]
        elif isinstance(data.get("itemInfo"), dict) and isinstance(
            data["itemInfo"].get("itemStruct"), dict
        ):
            data = data["itemInfo"]["itemStruct"]

        return data

    @staticmethod
    def _http_error_detail(response: httpx.Response) -> str:
        """Extract a concise error message from FastAPI or plain responses."""
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip().replace("\n", " ")[:300]

        detail: object = payload.get("detail", payload) if isinstance(payload, dict) else payload
        if isinstance(detail, dict):
            message = str(detail.get("message") or detail.get("error") or "").strip()
            attempts = detail.get("attempts")
            if attempts and message:
                return f"{message}（已尝试 {attempts} 次）"[:300]
            if message:
                return message[:300]
        if isinstance(detail, str):
            return detail.strip().replace("\n", " ")[:300]
        return str(detail).strip().replace("\n", " ")[:300]
