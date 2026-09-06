"""cleaner.py

清洗模块 - 调用 OpenAI 兼容 API 进行文本清洗和重组。

Notes:
- ASR 文本常常不带标点；标点/分段主要依赖 LLM 清洗。
- 线上模型偶发超时/限流/500 时，本模块提供“自动拆分再清洗”的兜底，
  以提升整体成功率（宁可分多次成功，也不要整块失败回退到原始文本）。
"""
import os
import asyncio
import yaml
import httpx
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, Dict, Any, Callable

config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)


FILENAME_PROMPT = """根据以下视频描述，生成一个简洁的文件名（不超过12个中文字符）。
要求：
1. 提取核心主题
2. 不要包含特殊字符和标点
3. 只输出文件名，不要任何解释

视频描述：
{desc}

文件名："""

CLEAN_PROMPT = """Clean and reorganize this speech-to-text transcript. Follow these rules strictly:

1. Add proper punctuation and paragraph breaks
2. Remove filler words (Chinese: "嗯", "啊", "那个", "就是说"; English: "um", "uh", "like", "you know")
3. Fix obvious speech recognition errors and typos
4. Keep the original meaning - do not add or remove substantial content
5. Make the text structure clear and readable
6. Output plain text, do not use Markdown formatting
7. **ABSOLUTELY CRITICAL: PRESERVE THE ORIGINAL LANGUAGE. DO NOT TRANSLATE ANYTHING.**
   - If the text below is in English → Your output MUST be 100% English
   - If the text below is in Chinese → Your output MUST be 100% Chinese
   - NEVER mix languages or translate any part of the text

Text to clean:
{text}

Cleaned text (same language as input):"""


class Cleaner:
    def __init__(self):
        sf_config = config['siliconflow']
        self.api_key = sf_config['api_key']
        self.base_url = sf_config['base_url']
        self.model = sf_config['model']
        self.reasoning_effort = str(sf_config.get('reasoning_effort', '') or '').strip()
        self.proxies: Optional[Dict[str, Any]] = None
        # 单次请求超时时间（秒）。超时太短会导致大段文本经常失败。
        self.timeout = float(sf_config.get('timeout', 240) or 240)
        self.max_retries = int(sf_config.get('max_retries', 3) or 3)
        self.retry_base_delay = float(sf_config.get('retry_base_delay', 5) or 5)
        self.retry_max_delay = float(sf_config.get('retry_max_delay', 90) or 90)
        self.concurrency = max(1, int(sf_config.get('concurrency', 1) or 1))
        self.status_callback: Optional[Callable[[str], None]] = None
        self.trust_env = False

        # 兜底拆分策略：当请求在重试后仍失败，自动把文本拆小再清洗。
        # depth 越大拆得越细；一般 2~4 足够。
        self.split_max_depth = int(sf_config.get('split_max_depth', 3) or 3)
        self.split_min_chars = int(sf_config.get('split_min_chars', 700) or 700)
        self.split_window = int(sf_config.get('split_window', 200) or 200)
        self.max_tokens = int(sf_config.get('max_tokens', 2048) or 2048)

    def _http_timeout(self, base: float) -> httpx.Timeout:
        """Create a more explicit timeout profile for httpx."""
        # connect/write/pool 通常不需要太长；read 由 base 控制。
        return httpx.Timeout(
            timeout=base,
            connect=min(30.0, base),
            read=base,
            write=min(30.0, base),
            pool=min(30.0, base),
        )

    def _choose_split_point(self, text: str) -> int:
        """Pick a split point near the middle on a natural boundary."""
        if not text:
            return 0
        mid = len(text) // 2
        w = int(self.split_window)
        left = max(0, mid - w)
        right = min(len(text), mid + w)
        window = text[left:right]

        # Prefer paragraph boundaries.
        candidates = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", "，", ",", "、", " "]
        best: Optional[int] = None
        best_score: Optional[int] = None

        for sep in candidates:
            idx = window.find(sep)
            if idx == -1:
                continue
            # split after separator if possible
            split_at = left + idx + len(sep)
            score = abs(split_at - mid)
            if best is None or best_score is None or score < best_score:
                best = split_at
                best_score = score

        if best is None:
            return mid
        return best

    def _retry_delay(self, attempt: int, response: Optional[httpx.Response] = None) -> float:
        """Calculate retry delay, honoring Retry-After when the API provides it."""
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), self.retry_max_delay)
                except ValueError:
                    try:
                        retry_at = parsedate_to_datetime(retry_after)
                        if retry_at.tzinfo is None:
                            retry_at = retry_at.replace(tzinfo=timezone.utc)
                        delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
                        return min(max(delay, 0.0), self.retry_max_delay)
                    except (TypeError, ValueError):
                        pass

        delay = min(self.retry_max_delay, self.retry_base_delay * (2 ** attempt))
        return delay + random.uniform(0, min(1.5, delay * 0.15))

    def _is_retryable_status(self, status_code: int) -> bool:
        return status_code == 429 or status_code in {500, 502, 503, 504}

    def _status(self, msg: str):
        print(msg)
        if self.status_callback:
            self.status_callback(msg)

    def _apply_model_options(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        return payload

    async def _post_chat_completions(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        context: str,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        retries = max(1, int(self.max_retries if max_retries is None else max_retries))
        last_error: Optional[Exception] = None

        for attempt in range(retries):
            try:
                timeout = self._http_timeout(float(self.timeout))
                client_kwargs: Dict[str, Any] = {"timeout": timeout, "trust_env": self.trust_env}
                if self.proxies is not None:
                    client_kwargs["proxies"] = self.proxies

                async with httpx.AsyncClient(**client_kwargs) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                    if self._is_retryable_status(response.status_code) and attempt < retries - 1:
                        wait_time = self._retry_delay(attempt, response)
                        detail = response.text.strip().replace("\n", " ")[:300]
                        self._status(
                            f"{context}请求返回 {response.status_code}，等待{wait_time:.1f}秒后重试..."
                            f" (尝试 {attempt + 1}/{retries})"
                            + (f" 详情: {detail}" if detail else "")
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    return response.json()

            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError, httpx.RemoteProtocolError, httpx.NetworkError) as e:
                last_error = e
                if attempt < retries - 1:
                    wait_time = self._retry_delay(attempt)
                    self._status(f"{context}请求异常 {type(e).__name__}，等待{wait_time:.1f}秒后重试... (尝试 {attempt + 1}/{retries})")
                    await asyncio.sleep(wait_time)
                    continue
                raise
            except httpx.HTTPStatusError as e:
                last_error = e
                if self._is_retryable_status(e.response.status_code) and attempt < retries - 1:
                    wait_time = self._retry_delay(attempt, e.response)
                    self._status(f"{context}请求失败 {e.response.status_code}，等待{wait_time:.1f}秒后重试... (尝试 {attempt + 1}/{retries})")
                    await asyncio.sleep(wait_time)
                    continue
                raise

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"{context}请求失败")
    
    async def generate_filename(self, desc: str) -> str:
        """根据视频描述生成文件名"""
        if not self.api_key:
            raise ValueError("请在config.yaml中配置 OpenAI 兼容 API Key")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = self._apply_model_options({
            "model": self.model,
            "messages": [
                {"role": "user", "content": FILENAME_PROMPT.format(desc=desc)}
            ],
            "temperature": 0.3,
            "max_tokens": 50,
            "stream": False,
        })
        
        result = await self._post_chat_completions(payload, headers, "文件名生成")
        filename = result['choices'][0]['message']['content'].strip()
        # 清理文件名中的非法字符
        import re
        filename = re.sub(r'[\\/:*?"<>|]', '', filename)
        return filename[:12] if len(filename) > 12 else filename
    
    async def clean_text(self, text: str, max_retries: Optional[int] = None) -> str:
        """清洗单个文本块"""
        if not self.api_key:
            raise ValueError("请在config.yaml中配置 OpenAI 兼容 API Key")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = self._apply_model_options({
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a text editor. You must preserve the original language of the input text. Never translate. If input is English, output must be English. If input is Chinese, output must be Chinese."},
                {"role": "user", "content": CLEAN_PROMPT.format(text=text)}
            ],
            "temperature": 0.2,
            "max_tokens": int(self.max_tokens),
            "stream": False,
        })
        
        result = await self._post_chat_completions(payload, headers, "文本清洗", max_retries=max_retries)
        return result['choices'][0]['message']['content'].strip()

    async def clean_text_smart(self, text: str, depth: int = 0) -> str:
        """更稳健的清洗：失败后自动拆分再清洗，提高整体成功率。"""
        text = (text or "").strip()
        if not text:
            return ""

        try:
            return await self.clean_text(text)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.NetworkError, httpx.HTTPStatusError) as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429:
                raise
            # 只有“还够长”且“没拆太深”才尝试拆分兜底，否则直接抛出让上层回退。
            if depth >= int(self.split_max_depth) or len(text) < int(self.split_min_chars):
                raise

            split_at = self._choose_split_point(text)
            left = text[:split_at].strip()
            right = text[split_at:].strip()

            # 防止极端情况 split 不动
            if not left or not right:
                raise

            # 递归拆分
            cleaned_left = await self.clean_text_smart(left, depth=depth + 1)
            cleaned_right = await self.clean_text_smart(right, depth=depth + 1)
            return (cleaned_left.strip() + "\n\n" + cleaned_right.strip()).strip()
    
    async def clean_chunks(self, chunks: list, progress_callback=None) -> list:
        """清洗所有文本块"""
        total = len(chunks)
        if total == 0:
            return []

        concurrency = min(self.concurrency, total)
        sem = asyncio.Semaphore(concurrency)

        cleaned_chunks = [None] * total
        completed = 0

        async def _clean_one(index: int, chunk: dict):
            async with sem:
                try:
                    cleaned_text = await self.clean_text_smart(chunk['text'])
                    error = None
                except Exception as e:
                    # httpx.ReadTimeout 的 str(e) 可能是空串；这里打印类型 + repr 方便定位。
                    error = f"{type(e).__name__}: {repr(e)}"
                    self._status(f"分块清洗失败，已跳过: {error}")
                    cleaned_text = chunk['text']

                return index, {
                    'start': chunk['start'],
                    'end': chunk['end'],
                    'original': chunk['text'],
                    'cleaned': cleaned_text,
                    'error': error
                }

        tasks = [asyncio.create_task(_clean_one(i, ch)) for i, ch in enumerate(chunks)]

        for fut in asyncio.as_completed(tasks):
            idx, item = await fut
            cleaned_chunks[idx] = item
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

        # typing: cleaned_chunks 已全部填充
        return cleaned_chunks  # type: ignore[return-value]
    
    def merge_to_markdown(self, cleaned_chunks: list, video_info: Optional[dict] = None) -> str:
        """合并为最终Markdown"""
        lines = []
        
        if video_info:
            lines.append(f"# {video_info.get('desc', '视频转写')}")
            lines.append("")
            if video_info.get('author'):
                lines.append(f"**作者**: {video_info['author']}")
            lines.append("")
            lines.append("---")
            lines.append("")
        
        for chunk in cleaned_chunks:
            lines.append(chunk['cleaned'])
            lines.append("")
        
        return "\n".join(lines)


async def main():
    """测试"""
    cleaner = Cleaner()
    
    test_text = "嗯今天呢我们来聊一聊就是说关于那个人工智能啊它其实是一个非常有意思的话题"
    
    print("原始文本:")
    print(test_text)
    print("\n清洗中...")
    
    try:
        cleaned = await cleaner.clean_text(test_text)
        print("\n清洗后:")
        print(cleaned)
    except ValueError as e:
        print(f"错误: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
