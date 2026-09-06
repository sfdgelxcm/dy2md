"""
Video to Markdown - 主程序入口
ETL Pipeline: 
1. 视频URL → 音频下载 → ASR转写 → 智能分块 → LLM清洗 → Markdown
2. 本地音频 → ASR转写 → 智能分块 → LLM清洗 → Markdown
"""
import os
import sys
import asyncio
import yaml
import glob
import re
from typing import Optional, Any, Dict, cast

# 确保能找到模块
sys.path.insert(0, os.path.dirname(__file__))

from downloader import DouyinDownloader
from transcriber import Transcriber
from chunker import Chunker
from cleaner import Cleaner
from url_utils import extract_http_url


class VideoToMarkdown:
    def __init__(self):
        # The Douyin HTTP adapter is initialized only for URL mode. Local
        # audio/text workflows do not depend on the external parsing service.
        self.downloader: Optional[DouyinDownloader] = None
        self.transcriber: Optional[Transcriber] = None  # 延迟加载，节省显存
        self.chunker = Chunker()
        self.cleaner = Cleaner()
        
        config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        raw_config = self.config.get('raw', {})
        self.raw_include_timestamps = raw_config.get('include_timestamps', True)
        
        self.output_dir = self.config['download']['output_dir']
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 创建raw子文件夹用于保存原始识别结果
        self.raw_dir = os.path.join(self.output_dir, 'raw')
        os.makedirs(self.raw_dir, exist_ok=True)
    
    def _ensure_transcriber(self):
        """延迟加载转写模型"""
        if self.transcriber is None:
            self.transcriber = Transcriber()

    def _ensure_downloader(self) -> DouyinDownloader:
        """延迟创建独立的抖音 HTTP 服务适配器。"""
        if self.downloader is None:
            self.downloader = DouyinDownloader(self.config)
        return self.downloader
    
    async def process_url(self, url: str, progress_callback=None) -> tuple:
        """处理抖音URL"""
        def report(step, msg):
            if progress_callback:
                progress_callback(step, 5, msg)
            print(f"[{step}/5] {msg}")

        clean_url = extract_http_url(url)
        if clean_url != (url or "").strip():
            report(1, f"已从分享文本提取链接: {clean_url}")
        
        # Step 1: 下载音频
        report(1, "正在获取视频信息并下载音频...")
        downloader = self._ensure_downloader()
        audio_path, video_info = await downloader.download_audio(clean_url)
        video_info = cast(Dict[str, Any], video_info)
        report(1, f"音频已下载: {os.path.basename(audio_path)}")
        
        # 调用音频处理
        output_path, markdown = await self._process_audio_internal(
            audio_path, video_info, progress_callback, start_step=2, delete_audio=True
        )
        return output_path, markdown
    
    async def process_audio(self, audio_path: str, progress_callback=None) -> tuple:
        """处理本地音频文件"""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        # 用文件名作为基础信息
        basename = os.path.splitext(os.path.basename(audio_path))[0]
        video_info = {'aweme_id': basename, 'desc': basename, 'author': ''}

        # For local audio, save the final markdown next to the audio file.
        local_out_dir = os.path.dirname(os.path.abspath(audio_path))
        
        return await self._process_audio_internal(
            audio_path,
            video_info,
            progress_callback,
            start_step=1,
            delete_audio=False,
            force_filename=basename,
            force_output_dir=local_out_dir,
        )
    
    async def process_audio_folder(self, folder_path: str, progress_callback=None) -> list:
        """批量处理文件夹中的音频"""
        if not os.path.isdir(folder_path):
            raise NotADirectoryError(f"文件夹不存在: {folder_path}")
        
        # 支持的音频格式
        audio_extensions = ['*.mp3', '*.wav', '*.m4a', '*.flac', '*.ogg', '*.mp4']
        audio_files = []
        for ext in audio_extensions:
            audio_files.extend(glob.glob(os.path.join(folder_path, ext)))
        
        if not audio_files:
            raise ValueError(f"文件夹中没有找到音频文件: {folder_path}")
        
        results = []
        total = len(audio_files)
        
        for i, audio_path in enumerate(audio_files):
            print(f"\n[批量处理 {i+1}/{total}] {os.path.basename(audio_path)}")
            try:
                output_path, markdown = await self.process_audio(audio_path, progress_callback)
                results.append({'file': audio_path, 'output': output_path, 'success': True})
            except Exception as e:
                print(f"处理失败: {e}")
                results.append({'file': audio_path, 'error': str(e), 'success': False})
        
        return results
    
    def _safe_filename(self, name: str) -> str:
        name = (name or "").strip()
        # Remove characters invalid on Windows filenames.
        name = re.sub(r'[\\/:*?"<>|]', '', name)
        # Avoid empty filename.
        return name or "output"

    async def _process_audio_internal(
        self,
        audio_path: str,
        video_info: dict,
        progress_callback=None,
        start_step=1,
        delete_audio=False,
        force_filename: str | None = None,
        force_output_dir: str | None = None,
    ) -> tuple:
        """内部音频处理流程"""
        total_steps = 4 if start_step == 1 else 5
        
        def report(step, msg):
            if progress_callback:
                progress_callback(step, total_steps, msg)
            print(f"[{step}/{total_steps}] {msg}")
        
        # ASR转写
        report(start_step, "正在进行语音识别...")
        self._ensure_transcriber()
        assert self.transcriber is not None
        segments, info = self.transcriber.transcribe(audio_path)
        report(start_step, f"识别完成: {len(segments)}个片段, 时长{info.duration:.1f}秒")
        
        # 保存原始识别结果到raw文件夹
        raw_filename = f"{video_info['aweme_id']}_raw.txt"
        raw_path = os.path.join(self.raw_dir, raw_filename)
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(f"# 原始语音识别结果\n")
            f.write(f"# 文件: {os.path.basename(audio_path)}\n")
            f.write(f"# 时长: {info.duration:.1f}秒\n")
            f.write(f"# 片段数: {len(segments)}\n")
            f.write(f"# 语言: {info.language} (概率: {info.language_probability:.2f})\n")
            f.write(f"\n{'='*60}\n\n")
            for seg in segments:
                if self.raw_include_timestamps:
                    f.write(f"[{seg['start']:.2f}s - {seg['end']:.2f}s] {seg['text']}\n")
                else:
                    f.write(f"{seg['text']}\n")
        report(start_step, f"原始结果已保存: {raw_path}")
        
        # 智能分块
        step2 = start_step + 1
        report(step2, "正在进行智能分块...")
        chunks = self.chunker.chunk_segments(segments)
        report(step2, f"分块完成: {len(chunks)}个文本块")
        
        # LLM清洗
        step3 = start_step + 2
        report(step3, f"正在进行AI清洗 (共{len(chunks)}块)...")
        
        def clean_progress(current, total):
            if progress_callback:
                progress_callback(step3, total_steps, f"AI清洗中: {current}/{total}")
        
        old_status_callback = self.cleaner.status_callback
        self.cleaner.status_callback = lambda msg: report(step3, msg)
        try:
            cleaned_chunks = await self.cleaner.clean_chunks(chunks, clean_progress)
        finally:
            self.cleaner.status_callback = old_status_callback
        report(step3, "AI清洗完成")
        
        # 生成Markdown
        step4 = start_step + 3
        report(step4, "正在生成Markdown...")
        markdown = self.cleaner.merge_to_markdown(cleaned_chunks, video_info)
        
        # 生成文件名
        if force_filename:
            filename = self._safe_filename(force_filename)
        else:
            desc = video_info.get('desc', '')
            if desc:
                try:
                    filename = await self.cleaner.generate_filename(desc)
                except Exception as e:
                    report(step4, f"AI文件名生成失败，改用视频ID/描述命名: {type(e).__name__}")
                    fallback_name = video_info.get('aweme_id') or desc[:30] or 'output'
                    filename = self._safe_filename(str(fallback_name))
            else:
                filename = self._safe_filename(video_info.get('aweme_id', 'output'))
        
        # 保存文件
        output_filename = f"{filename}.md"
        out_dir = force_output_dir or self.output_dir
        os.makedirs(out_dir, exist_ok=True)
        output_path = os.path.join(out_dir, output_filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)
        
        report(step4, f"完成! 已保存到: {output_path}")
        
        # 清理临时文件
        if delete_audio and os.path.exists(audio_path):
            os.remove(audio_path)
        
        return output_path, markdown
    
    # 保持向后兼容
    async def process(self, url: str, progress_callback=None) -> tuple:
        return await self.process_url(url, progress_callback)


async def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description='Video to Markdown ETL Pipeline')
    parser.add_argument('input', help='抖音视频URL / 本地音频文件路径 / 音频文件夹路径')
    parser.add_argument('-o', '--output', help='输出目录')
    parser.add_argument('--batch', action='store_true', help='批量处理文件夹')
    args = parser.parse_args()
    
    pipeline = VideoToMarkdown()
    
    if args.output:
        pipeline.output_dir = args.output
        os.makedirs(args.output, exist_ok=True)
    
    input_path = args.input
    
    # 判断输入类型
    if args.batch or os.path.isdir(input_path):
        # 批量处理文件夹
        print(f"批量处理文件夹: {input_path}")
        results = await pipeline.process_audio_folder(input_path)
        success = sum(1 for r in results if r['success'])
        print(f"\n完成! 成功: {success}/{len(results)}")
    elif os.path.isfile(input_path):
        # 本地音频文件
        print(f"处理本地音频: {input_path}")
        output_path, _ = await pipeline.process_audio(input_path)
        print(f"\n输出文件: {output_path}")
    else:
        # URL
        output_path, _ = await pipeline.process_url(input_path)
        print(f"\n输出文件: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
