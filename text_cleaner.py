"""
独立文本清洗工具 - 直接清洗文本文件
支持：
1. 单个文本文件清洗
2. 批量文件夹清洗
3. 直接文本输入清洗
"""
import os
import sys
import asyncio
import yaml
import glob
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(__file__))

from cleaner import Cleaner
from chunker import Chunker


class TextCleaner:
    def __init__(self):
        self.cleaner = Cleaner()
        self.chunker = Chunker()
        
        config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.output_dir = self.config['download']['output_dir']
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _split_text_to_chunks(self, text: str) -> list:
        """将长文本按字符数分块"""
        max_chars = self.config['chunking']['max_chars']
        
        # 按段落分割
        paragraphs = text.split('\n')
        
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) + 1 <= max_chars:
                current_chunk += para + "\n"
            else:
                if current_chunk.strip():
                    chunks.append({
                        'start': 0,
                        'end': 0,
                        'text': current_chunk.strip()
                    })
                current_chunk = para + "\n"
        
        if current_chunk.strip():
            chunks.append({
                'start': 0,
                'end': 0,
                'text': current_chunk.strip()
            })
        
        return chunks

    def _read_text_file(self, input_path: str) -> str:
        """Read text with common encodings (utf-8/gb18030) to avoid decode failures."""
        encodings = ["utf-8", "utf-8-sig", "gb18030", "gbk"]
        last_error = None
        for enc in encodings:
            try:
                with open(input_path, 'r', encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError as e:
                last_error = e
        raise UnicodeDecodeError(
            last_error.encoding if last_error else "unknown",
            last_error.object if last_error else b"",
            last_error.start if last_error else 0,
            last_error.end if last_error else 0,
            f"Unable to decode file using {', '.join(encodings)}"
        )
    
    async def clean_text(self, text: str, progress_callback=None) -> str:
        """清洗纯文本"""
        print("正在分块...")
        chunks = self._split_text_to_chunks(text)
        print(f"已分成 {len(chunks)} 个文本块")
        
        print("正在AI清洗...")
        def clean_progress(current, total):
            if progress_callback:
                progress_callback(current, total)
            print(f"  进度: {current}/{total}")
        
        cleaned_chunks = await self.cleaner.clean_chunks(chunks, clean_progress)
        print("清洗完成")
        
        # 合并清洗后的文本
        cleaned_text = "\n\n".join([chunk['cleaned'] for chunk in cleaned_chunks])
        return cleaned_text
    
    async def clean_file(self, input_path: str, output_path: Optional[str] = None, progress_callback=None) -> str:
        """清洗单个文本文件"""
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"文件不存在: {input_path}")
        
        print(f"读取文件: {input_path}")
        text = self._read_text_file(input_path)
        
        if not text.strip():
            raise ValueError("文件内容为空")
        
        print(f"文件大小: {len(text)} 字符")
        
        # 清洗文本
        cleaned_text = await self.clean_text(text, progress_callback)
        
        # 生成输出路径
        if output_path is None:
            basename = os.path.splitext(os.path.basename(input_path))[0]
            # Keep output filename consistent with input filename.
            output_path = os.path.join(self.output_dir, f"{basename}.md")
        
        # 保存文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_text)
        
        print(f"已保存到: {output_path}")
        return output_path

    async def clean_files(self, file_paths: list, progress_callback=None) -> list:
        """Batch clean multiple text files."""
        if not file_paths:
            raise ValueError("No input files provided")

        results = []
        total = len(file_paths)

        for i, file_path in enumerate(file_paths, start=1):
            print(f"\n[Batch {i}/{total}] {os.path.basename(file_path)}")
            try:
                output_path = await self.clean_file(file_path, progress_callback=progress_callback)
                results.append({'file': file_path, 'output': output_path, 'success': True})
            except Exception as e:
                print(f"Failed: {e}")
                results.append({'file': file_path, 'error': str(e), 'success': False})

        return results
    
    async def clean_folder(self, folder_path: str, progress_callback=None) -> list:
        """批量清洗文件夹中的文本文件"""
        if not os.path.isdir(folder_path):
            raise NotADirectoryError(f"文件夹不存在: {folder_path}")
        
        # 支持的文本格式
        text_extensions = ['*.txt', '*.md', '*.text']
        text_files = []
        for ext in text_extensions:
            text_files.extend(glob.glob(os.path.join(folder_path, ext)))
        
        if not text_files:
            raise ValueError(f"文件夹中没有找到文本文件: {folder_path}")
        
        results = []
        total = len(text_files)
        
        for i, file_path in enumerate(text_files):
            print(f"\n[批量处理 {i+1}/{total}] {os.path.basename(file_path)}")
            try:
                output_path = await self.clean_file(file_path, progress_callback=progress_callback)
                results.append({'file': file_path, 'output': output_path, 'success': True})
            except Exception as e:
                print(f"处理失败: {e}")
                results.append({'file': file_path, 'error': str(e), 'success': False})
        
        return results


async def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description='独立文本清洗工具')
    parser.add_argument('input', nargs='+', help='文本文件路径 / 文件夹路径 / 直接输入文本')
    parser.add_argument('-o', '--output', help='输出文件路径（可选）')
    parser.add_argument('--batch', action='store_true', help='批量处理文件夹')
    parser.add_argument('--text', action='store_true', help='直接输入文本而非文件路径')
    args = parser.parse_args()
    
    cleaner = TextCleaner()
    
    def _print_results(results: list):
        success = sum(1 for r in results if r['success'])
        print(f"\n完成! 成功: {success}/{len(results)}")
        for r in results:
            if r['success']:
                print(f"✓ {os.path.basename(r['file'])} -> {os.path.basename(r['output'])}")
            else:
                print(f"✗ {os.path.basename(r['file'])}: {r['error']}")

    try:
        inputs = args.input

        if args.text:
            # 直接文本输入
            print("清洗文本...")
            cleaned = await cleaner.clean_text(" ".join(inputs))
            
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(cleaned)
                print(f"\n输出文件: {args.output}")
            else:
                print("\n清洗结果:")
                print("=" * 50)
                print(cleaned)
        
        elif args.batch:
            if len(inputs) == 1 and os.path.isdir(inputs[0]):
                # 批量处理文件夹
                print(f"批量处理文件夹: {inputs[0]}")
                results = await cleaner.clean_folder(inputs[0])
            else:
                # 批量处理多个文件
                print(f"批量处理多个文件: {len(inputs)}")
                results = await cleaner.clean_files(inputs)
            _print_results(results)

        elif len(inputs) > 1:
            # 批量处理多个文件
            results = await cleaner.clean_files(inputs)
            _print_results(results)

        elif os.path.isdir(inputs[0]):
            # 批量处理文件夹
            print(f"批量处理文件夹: {inputs[0]}")
            results = await cleaner.clean_folder(inputs[0])
            _print_results(results)

        else:
            # 单个文件
            output_path = await cleaner.clean_file(inputs[0], args.output)
            print(f"\n输出文件: {output_path}")
    
    except Exception as e:
        import traceback
        print(f"错误: {e}")
        print("\n详细错误信息:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
