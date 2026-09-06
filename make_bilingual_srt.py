"""make_bilingual_srt.py

Generate bilingual (EN + ZH) subtitles from an English audio/video file.

- ASR: faster-whisper (word timestamps)
- Segmentation: punctuation-first, with duration/length/gap safeguards
- Translation: SiliconFlow chat/completions (config in config.yaml)

Run with the Python environment that has faster-whisper installed, e.g.:
  python make_bilingual_srt.py "D:\path\to\audio.mp3"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
import yaml


def _disable_proxy_env() -> None:
    """Disable proxy env vars for httpx/huggingface.

    Some environments have ALL_PROXY/HTTP(S)_PROXY set to a SOCKS proxy.
    huggingface_hub uses httpx and will error if socksio is not installed.
    """

    for k in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(k, None)



_SENT_END_RE = re.compile(r"[.!?]+[\"')\]]*$")


def _load_config(script_dir: Path) -> Dict[str, Any]:
    config_path = script_dir / "config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _ts_srt(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000.0))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        # Drop first fence line and last fence if present.
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return s


def _collapse_spaces(s: str) -> str:
    # Keep English readable; avoid weird double spaces from word tokens.
    return re.sub(r"\s+", " ", (s or "").strip())


@dataclass
class SubtitleLine:
    start: float
    end: float
    en: str
    zh: str = ""


class SiliconFlowTranslator:
    def __init__(self, sf_config: Dict[str, Any]):
        self.api_key = (sf_config.get("api_key") or "").strip()
        self.base_url = (sf_config.get("base_url") or "https://api.siliconflow.cn/v1").strip().rstrip("/")
        self.model = (sf_config.get("model") or "").strip()

        if not self.api_key:
            raise ValueError("Missing SiliconFlow api_key in config.yaml")
        if not self.model:
            raise ValueError("Missing SiliconFlow model in config.yaml")

        # Use explicit timeouts; translation is usually fast.
        self.timeout_s = float(sf_config.get("translate_timeout", 60) or 60)
        self.max_retries = int(sf_config.get("translate_max_retries", 3) or 3)
        self.trust_env = False  # avoid picking up system proxy env

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _post_chat(self, client: httpx.AsyncClient, payload: Dict[str, Any]) -> str:
        url = f"{self.base_url}/chat/completions"
        resp = await client.post(url, headers=self._headers(), json=payload)
        resp.raise_for_status()
        data = resp.json()
        return (data["choices"][0]["message"]["content"] or "").strip()

    async def translate_lines(self, lines: Sequence[str], *, batch_size: int = 20) -> List[str]:
        """Translate EN lines to ZH, preserving 1:1 ordering."""
        texts = [(_collapse_spaces(x) if x else "") for x in lines]
        out: List[str] = ["" for _ in texts]

        async with httpx.AsyncClient(timeout=self.timeout_s, trust_env=self.trust_env) as client:
            for start in range(0, len(texts), batch_size):
                chunk = texts[start : start + batch_size]
                translated = await self._translate_chunk_robust(client, chunk)
                out[start : start + batch_size] = translated

        return out

    async def _translate_chunk_robust(self, client: httpx.AsyncClient, chunk: Sequence[str]) -> List[str]:
        # Empty lines pass through.
        if not chunk:
            return []
        if all(not x.strip() for x in chunk):
            return ["" for _ in chunk]

        # Prefer JSON-array output to keep alignment.
        system = (
            "You are a professional translator. Translate English to Simplified Chinese. "
            "Keep it natural and fluent. Do not add explanations. "
            "Return ONLY a valid JSON array of strings with the same length as the input array."
        )
        user = "Input JSON array (English lines):\n" + json.dumps(list(chunk), ensure_ascii=False)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
        }

        last_err: Optional[Exception] = None
        for attempt in range(max(1, self.max_retries)):
            try:
                content = await self._post_chat(client, payload)
                content = _strip_code_fences(content)
                arr = json.loads(content)
                if not isinstance(arr, list):
                    raise ValueError("Translator did not return a JSON array")
                if len(arr) != len(chunk):
                    raise ValueError(f"Translator returned {len(arr)} items, expected {len(chunk)}")
                return [str(x).strip() for x in arr]
            except Exception as e:
                last_err = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue

        # Fallback: split batch.
        if len(chunk) == 1:
            # Last resort: translate single line without JSON.
            return [await self._translate_single(client, chunk[0])]

        mid = len(chunk) // 2
        left = await self._translate_chunk_robust(client, chunk[:mid])
        right = await self._translate_chunk_robust(client, chunk[mid:])
        return left + right

    async def _translate_single(self, client: httpx.AsyncClient, text: str) -> str:
        text = _collapse_spaces(text)
        if not text:
            return ""
        prompt = (
            "Translate the following English text to Simplified Chinese. "
            "Only output the Chinese translation, no explanations.\n\n"
            f"English: {text}\nChinese:"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 512,
        }
        for attempt in range(max(1, self.max_retries)):
            try:
                content = await self._post_chat(client, payload)
                return (content or "").strip()
            except Exception:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
                else:
                    raise


def _should_break_on_punct(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_SENT_END_RE.search(t))


def _extract_words(segments: Iterable[Any]) -> List[Tuple[float, float, str]]:
    words: List[Tuple[float, float, str]] = []
    for seg in segments:
        seg_words = getattr(seg, "words", None)
        if not seg_words:
            continue
        for w in seg_words:
            ws = float(getattr(w, "start", 0.0) or 0.0)
            we = float(getattr(w, "end", ws) or ws)
            wt = str(getattr(w, "word", "") or "")
            if wt.strip() == "":
                continue
            words.append((ws, we, wt))
    return words


def regroup_words_to_subtitles(
    words: Sequence[Tuple[float, float, str]],
    *,
    max_duration: float = 6.0,
    hard_max_duration: float = 7.0,
    min_duration: float = 1.2,
    en_max_chars: int = 66,
    en_hard_max_chars: int = 72,
    gap_threshold: float = 0.6,
) -> List[SubtitleLine]:
    """Build subtitle lines from word-level timestamps.

    Rules:
    - Prefer breaking on sentence-ending punctuation.
    - Otherwise break on max duration / max chars / large gaps.
    - Avoid too-short lines unless forced by hard limits.
    """

    if not words:
        return []

    lines: List[SubtitleLine] = []
    buf_tokens: List[str] = []
    line_start = words[0][0]
    line_end = words[0][1]

    def buf_text() -> str:
        return _collapse_spaces("".join(buf_tokens))

    def flush(force: bool = False) -> None:
        nonlocal buf_tokens, line_start, line_end
        text = buf_text()
        if not text:
            buf_tokens = []
            return
        dur = max(0.0, line_end - line_start)
        if not force and dur < min_duration and lines:
            # Merge into previous line if possible.
            prev = lines[-1]
            prev.en = _collapse_spaces(prev.en + " " + text)
            prev.end = max(prev.end, line_end)
        else:
            lines.append(SubtitleLine(start=line_start, end=line_end, en=text))
        buf_tokens = []

    n = len(words)
    for i, (ws, we, wt) in enumerate(words):
        if not buf_tokens:
            line_start = ws
        buf_tokens.append(wt)
        line_end = we

        next_start = words[i + 1][0] if i + 1 < n else None
        gap = (next_start - we) if next_start is not None else 0.0

        text = buf_text()
        dur = max(0.0, line_end - line_start)

        # Hard stops.
        if dur >= hard_max_duration or len(text) >= en_hard_max_chars:
            flush(force=True)
            continue

        # Prefer punctuation break.
        if _should_break_on_punct(text) and dur >= min_duration:
            flush(force=True)
            continue

        # Soft breaks.
        if dur >= max_duration and dur >= min_duration:
            flush(force=True)
            continue

        if len(text) >= en_max_chars and dur >= min_duration:
            flush(force=True)
            continue

        if gap_threshold > 0 and gap >= gap_threshold and dur >= min_duration:
            flush(force=True)
            continue

    # Flush remaining.
    if buf_tokens:
        flush(force=True)

    # Final cleanup: drop ultra-short empty-ish entries.
    cleaned: List[SubtitleLine] = []
    for ln in lines:
        ln.en = _collapse_spaces(ln.en)
        if ln.en:
            cleaned.append(ln)
    return cleaned


def _iter_media_files(input_path: Path, exts: Sequence[str]) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    found: List[Path] = []
    for ext in exts:
        ext = ext.lower().lstrip(".")
        found.extend(sorted(input_path.glob(f"*.{ext}")))
    # stable order
    return sorted(set(found), key=lambda p: p.name.lower())


def _write_srt(path: Path, lines: Sequence[SubtitleLine], *, bom: bool = True) -> None:
    enc = "utf-8-sig" if bom else "utf-8"
    with path.open("w", encoding=enc, newline="\n") as f:
        for idx, ln in enumerate(lines, start=1):
            f.write(str(idx) + "\n")
            f.write(f"{_ts_srt(ln.start)} --> {_ts_srt(ln.end)}\n")
            f.write((ln.en or "").strip() + "\n")
            f.write((ln.zh or "").strip() + "\n\n")


async def process_one(
    audio_path: Path,
    out_path: Path,
    *,
    whisper_cfg: Dict[str, Any],
    translator: SiliconFlowTranslator,
    max_duration: float,
    hard_max_duration: float,
    min_duration: float,
    en_max_chars: int,
    en_hard_max_chars: int,
    gap_threshold: float,
    translate_batch_size: int,
    vad_min_silence_ms: int,
    vad_speech_pad_ms: int,
    bom: bool,
    overwrite: bool,
) -> None:
    if out_path.exists() and not overwrite:
        print(f"[skip] exists: {out_path}")
        return

    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "faster-whisper is not available in this Python environment. "
            "Run this script with the venv that has faster-whisper installed."
        ) from e

    model_size = whisper_cfg.get("model_size") or "large-v3"
    device = whisper_cfg.get("device") or "cuda"
    compute_type = whisper_cfg.get("compute_type") or "float16"

    language = whisper_cfg.get("language", None)
    # Force English if unset.
    if not language:
        language = "en"

    print(f"[asr] {audio_path.name}")
    t0 = time.time()
    model = WhisperModel(str(model_size), device=str(device), compute_type=str(compute_type))

    segments, _info = model.transcribe(
        str(audio_path),
        language=str(language),
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": int(vad_min_silence_ms),
            "speech_pad_ms": int(vad_speech_pad_ms),
        },
        word_timestamps=True,
        beam_size=5,
    )

    words = _extract_words(segments)
    lines = regroup_words_to_subtitles(
        words,
        max_duration=max_duration,
        hard_max_duration=hard_max_duration,
        min_duration=min_duration,
        en_max_chars=en_max_chars,
        en_hard_max_chars=en_hard_max_chars,
        gap_threshold=gap_threshold,
    )

    en_texts = [ln.en for ln in lines]
    print(f"[asr] {len(lines)} subtitle lines, {time.time() - t0:.1f}s")

    print(f"[translate] {audio_path.name}")
    zh_texts = await translator.translate_lines(en_texts, batch_size=translate_batch_size)
    if len(zh_texts) != len(lines):
        raise RuntimeError("Translation line count mismatch")
    for ln, zh in zip(lines, zh_texts):
        ln.zh = (zh or "").strip()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_srt(out_path, lines, bom=bom)
    print(f"[ok] {out_path}")


async def amain(argv: Optional[Sequence[str]] = None) -> int:
    _disable_proxy_env()

    p = argparse.ArgumentParser(description="Generate bilingual (EN+ZH) SRT using faster-whisper + SiliconFlow")
    p.add_argument("input", help="Input media file or a directory")
    p.add_argument("-o", "--output", help="Output .srt file (if input is a file) or output directory (if input is a dir)")
    p.add_argument("--ext", nargs="*", default=["mp3", "m4a", "wav", "flac", "ogg", "mp4", "mkv"], help="Extensions for directory mode")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing .srt")
    p.add_argument("--no-bom", action="store_true", help="Write UTF-8 without BOM")

    # Segmentation knobs (defaults are the recommended set).
    p.add_argument("--max-duration", type=float, default=6.0)
    p.add_argument("--hard-max-duration", type=float, default=7.0)
    p.add_argument("--min-duration", type=float, default=1.2)
    p.add_argument("--en-max-chars", type=int, default=66)
    p.add_argument("--en-hard-max-chars", type=int, default=72)
    p.add_argument("--gap-threshold", type=float, default=0.6)

    # VAD knobs
    p.add_argument("--vad-min-silence-ms", type=int, default=800)
    p.add_argument("--vad-speech-pad-ms", type=int, default=200)

    # Translation batching
    p.add_argument("--translate-batch-size", type=int, default=20)

    args = p.parse_args(argv)

    script_dir = Path(__file__).resolve().parent
    cfg = _load_config(script_dir)
    whisper_cfg = dict(cfg.get("whisper") or {})
    sf_cfg = dict(cfg.get("siliconflow") or {})

    inp = Path(args.input).expanduser().resolve()
    if not inp.exists():
        raise FileNotFoundError(f"Input not found: {inp}")

    translator = SiliconFlowTranslator(sf_cfg)

    bom = not bool(args.no_bom)
    overwrite = bool(args.overwrite)

    if inp.is_file():
        out = Path(args.output).expanduser().resolve() if args.output else inp.with_suffix(".bilingual.srt")
        await process_one(
            inp,
            out,
            whisper_cfg=whisper_cfg,
            translator=translator,
            max_duration=float(args.max_duration),
            hard_max_duration=float(args.hard_max_duration),
            min_duration=float(args.min_duration),
            en_max_chars=int(args.en_max_chars),
            en_hard_max_chars=int(args.en_hard_max_chars),
            gap_threshold=float(args.gap_threshold),
            translate_batch_size=int(args.translate_batch_size),
            vad_min_silence_ms=int(args.vad_min_silence_ms),
            vad_speech_pad_ms=int(args.vad_speech_pad_ms),
            bom=bom,
            overwrite=overwrite,
        )
        return 0

    # Directory mode
    out_dir = Path(args.output).expanduser().resolve() if args.output else inp
    files = _iter_media_files(inp, args.ext)
    if not files:
        print(f"No media files found in: {inp}")
        return 2

    for f in files:
        out = out_dir / f"{f.stem}.bilingual.srt"
        await process_one(
            f,
            out,
            whisper_cfg=whisper_cfg,
            translator=translator,
            max_duration=float(args.max_duration),
            hard_max_duration=float(args.hard_max_duration),
            min_duration=float(args.min_duration),
            en_max_chars=int(args.en_max_chars),
            en_hard_max_chars=int(args.en_hard_max_chars),
            gap_threshold=float(args.gap_threshold),
            translate_batch_size=int(args.translate_batch_size),
            vad_min_silence_ms=int(args.vad_min_silence_ms),
            vad_speech_pad_ms=int(args.vad_speech_pad_ms),
            bom=bom,
            overwrite=overwrite,
        )

    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(amain()))
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
