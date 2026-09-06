"""
转写模块 - 使用 faster-whisper 将音频转为文字
"""
import os
import yaml
from faster_whisper import WhisperModel

config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)


class Transcriber:
    def __init__(self):
        whisper_config = config['whisper']
        self.model = WhisperModel(
            whisper_config['model_size'],
            device=whisper_config['device'],
            compute_type=whisper_config['compute_type']
        )
        self.language = whisper_config['language']
    
    def transcribe(self, audio_path: str) -> list:
        """
        转写音频文件
        返回: [(start, end, text), ...]
        """
        segments, info = self.model.transcribe(
            audio_path,
            language=self.language,
            vad_filter=True,  # 过滤静音
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        results = []
        for seg in segments:
            results.append({
                'start': seg.start,
                'end': seg.end,
                'text': seg.text.strip()
            })
        
        return results, info


def main():
    """测试"""
    transcriber = Transcriber()
    
    test_audio = "./temp/7585068005202119987.mp3"
    if not os.path.exists(test_audio):
        print(f"测试文件不存在: {test_audio}")
        return
    
    print("开始转写...")
    segments, info = transcriber.transcribe(test_audio)
    
    print(f"语言: {info.language}, 概率: {info.language_probability:.2f}")
    print(f"时长: {info.duration:.1f}秒")
    print(f"分段数: {len(segments)}")
    print("\n转写结果:")
    for seg in segments[:10]:
        print(f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")


if __name__ == "__main__":
    main()
