"""
URL input helpers.
"""
import re


_URL_RE = re.compile(
    r"https?://[^\s<>'\"“”‘’（）()，。；、]+"
    r"|(?<![\w.-])(?:www\.)?(?:v\.)?douyin\.com/[^\s<>'\"“”‘’（）()，。；、]+",
    re.IGNORECASE,
)

_TRAILING_PUNCTUATION = ".,;:!?)，。；：！？）】》>\"'“”‘’"


def extract_http_url(text: str) -> str:
    """Extract the first usable URL from a raw URL or copied share text."""
    source = (text or "").strip()
    if not source:
        raise ValueError("请输入抖音链接或包含抖音链接的分享文本")

    match = _URL_RE.search(source)
    if not match:
        raise ValueError("未找到有效链接，请粘贴完整抖音链接或包含 https:// 的分享文本")

    url = match.group(0).strip().rstrip(_TRAILING_PUNCTUATION)
    if not url:
        raise ValueError("未找到有效链接，请粘贴完整抖音链接或包含 https:// 的分享文本")

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    return url
