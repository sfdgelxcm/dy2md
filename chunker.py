"""
分块模块 - 按时间戳累积分块
"""
import os
import yaml

config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)


class Chunker:
    def __init__(self):
        self.max_chars = config['chunking']['max_chars']
        self.min_chars = config['chunking']['min_chars']
    
    def chunk_segments(self, segments: list) -> list:
        """
        将转写segments按字符数分块
        输入: [{'start': 0.0, 'end': 2.5, 'text': '...'}, ...]
        输出: [{'start': 0.0, 'end': 30.0, 'text': '合并后的文本'}, ...]
        """
        if not segments:
            return []
        
        chunks = []
        current_chunk = {
            'start': segments[0]['start'],
            'end': segments[0]['end'],
            'text': segments[0]['text'],
            'segments': [segments[0]]
        }
        
        for seg in segments[1:]:
            # 使用换行分隔，避免 ASR 片段直接粘连成一大坨（尤其在清洗失败回退时可读性很差）
            combined_text = current_chunk['text'].rstrip() + "\n" + seg['text'].lstrip()
            
            if len(combined_text) <= self.max_chars:
                current_chunk['text'] = combined_text
                current_chunk['end'] = seg['end']
                current_chunk['segments'].append(seg)
            else:
                if len(current_chunk['text']) >= self.min_chars:
                    chunks.append(current_chunk)
                    current_chunk = {
                        'start': seg['start'],
                        'end': seg['end'],
                        'text': seg['text'],
                        'segments': [seg]
                    }
                else:
                    current_chunk['text'] = combined_text
                    current_chunk['end'] = seg['end']
                    current_chunk['segments'].append(seg)
        
        if current_chunk['text']:
            chunks.append(current_chunk)
        
        return chunks
    
    def format_time(self, seconds: float) -> str:
        """格式化时间"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"


def main():
    """测试"""
    chunker = Chunker()
    
    test_segments = [
        {'start': 0.0, 'end': 5.0, 'text': '大家好今天我们来聊一聊'},
        {'start': 5.0, 'end': 10.0, 'text': '关于人工智能的一些话题'},
        {'start': 10.0, 'end': 15.0, 'text': '首先我们要了解什么是AI'},
    ]
    
    chunks = chunker.chunk_segments(test_segments)
    for i, chunk in enumerate(chunks):
        print(f"Chunk {i+1}: [{chunker.format_time(chunk['start'])} - {chunker.format_time(chunk['end'])}]")
        print(f"  Text: {chunk['text'][:50]}...")
        print(f"  Chars: {len(chunk['text'])}")


if __name__ == "__main__":
    main()
