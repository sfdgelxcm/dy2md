"""
翻译模块 - 调用硅基流动API进行文本翻译
"""
import os
import yaml
import httpx
import asyncio

config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)


class Translator:
    def __init__(self):
        sf_config = config['siliconflow']
        self.api_key = sf_config['api_key']
        self.base_url = sf_config['base_url']
        self.model = sf_config['model']
        
        # 强制禁用系统代理
        import os
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
    
    async def translate_to_chinese(self, text: str, max_retries: int = 3) -> str:
        """将英文翻译成中文"""
        if not self.api_key:
            raise ValueError("请在config.yaml中配置硅基流动API Key")
        
        prompt = f"""Translate the following English text to Chinese. 
Keep the translation natural and fluent.
Preserve paragraph breaks and structure.
Only output the Chinese translation, no explanations.

English text:
{text}

Chinese translation:"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 4096
        }
        
        last_error = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload
                    )
                    
                    if response.status_code == 500:
                        error_detail = response.text
                        print(f"API 500错误: {error_detail}")
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2
                            print(f"等待{wait_time}秒后重试... ({attempt + 1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            continue
                    
                    response.raise_for_status()
                    result = response.json()
                    return result['choices'][0]['message']['content'].strip()
                    
            except httpx.HTTPStatusError as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"请求失败，等待{wait_time}秒后重试... ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                last_error = e
                raise
        
        if last_error:
            raise last_error
    
    async def translate_file(self, input_file: str, output_file: str, chunk_size: int = 2000):
        """翻译整个文件，分块处理"""
        print(f"读取文件: {input_file}")
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 按段落分块
        paragraphs = content.split('\n\n')
        translated_paragraphs = []
        
        current_chunk = []
        current_length = 0
        total_chunks = 0
        
        # 计算总块数
        temp_length = 0
        for para in paragraphs:
            temp_length += len(para)
            if temp_length >= chunk_size:
                total_chunks += 1
                temp_length = 0
        total_chunks += 1
        
        chunk_num = 0
        
        for i, para in enumerate(paragraphs):
            if not para.strip():
                translated_paragraphs.append('')
                continue
            
            current_chunk.append(para)
            current_length += len(para)
            
            # 当达到块大小或是最后一段时，翻译当前块
            if current_length >= chunk_size or i == len(paragraphs) - 1:
                chunk_num += 1
                chunk_text = '\n\n'.join(current_chunk)
                print(f"\n翻译块 {chunk_num}/{total_chunks} ({len(chunk_text)} 字符)...")
                
                try:
                    translated = await self.translate_to_chinese(chunk_text)
                    translated_paragraphs.append(translated)
                except Exception as e:
                    print(f"翻译失败: {type(e).__name__}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    # 失败时保留原文
                    translated_paragraphs.append(chunk_text)
                
                current_chunk = []
                current_length = 0
        
        # 保存翻译结果
        final_text = '\n\n'.join(translated_paragraphs)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(final_text)
        
        print(f"\n翻译完成! 已保存到: {output_file}")
        return output_file


async def main():
    """命令行入口"""
    import argparse
    parser = argparse.ArgumentParser(description='翻译英文文件为中文')
    parser.add_argument('input', help='输入文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径（默认：原文件名_zh.md）')
    args = parser.parse_args()
    
    translator = Translator()
    
    # 生成输出文件名
    if args.output:
        output_file = args.output
    else:
        base, ext = os.path.splitext(args.input)
        output_file = f"{base}_zh{ext}"
    
    await translator.translate_file(args.input, output_file)


if __name__ == "__main__":
    asyncio.run(main())
