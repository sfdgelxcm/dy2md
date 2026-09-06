<div align="center">

# dy2md

**抖音视频 / 本地音视频 → Markdown** 的全自动 ETL 工具

媒体获取 → 语音识别 → AI 清洗 → 结构化 Markdown

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](#环境要求)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)](#快速开始)

</div>

---

## 这是什么

把一条抖音链接，或者一个本地音频/视频文件，丢给它，就能自动跑完「下载音频 → 语音识别 → AI 去除口水词并排版 → 输出 Markdown」全流程，最后得到一份可以直接读的文字稿。

-  **抖音视频转写**：粘贴分享链接或分享文案即可
-  **本地音视频转写**：mp3 / wav / m4a / flac / ogg / mp4
-  **批量处理**：整个文件夹一键跑完
-  **AI 智能清洗**：自动加标点、去口语词、修错字、重新分段
-  **智能文件名**：根据内容自动生成简洁文件名
-  **双语字幕**：英文音视频转写并生成中英双语 SRT
-  **独立文本清洗**：手头已有文字稿？不需要音频也能直接清洗排版
-  **GUI + CLI**：图形界面日常用，命令行方便自动化

## 快速开始

> 只处理**本地文件**？跳过第 1 步，直接看第 2 步即可，不需要部署抖音解析服务。

**1. 部署抖音解析服务**（仅处理抖音链接时需要，另开一个目录）

```powershell
git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API.git
cd Douyin_TikTok_Download_API
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
按该项目文档配置好 Cookie。**不需要手动启动它**——本项目的启动器会在需要时自动用它的独立环境拉起来。

**2. 安装本项目**

```powershell
git clone https://github.com/sfdgelxcm/dy2md.git
cd dy2md
setup.bat          # 或手动: python -m venv .venv && pip install -r requirements.txt
copy config.example.yaml config.yaml
```
打开 `config.yaml`，填好你的大模型 API（任意 OpenAI 兼容接口都行，见下方[配置说明](#大模型-api)），如果要处理抖音链接，把 `douyin_api.auto_start.project_dir` 指向第 1 步克隆的目录。

**3. 运行**

```powershell
run_gui_pro.bat
```
双击即可，GUI 会自动检测并按需拉起抖音解析服务。命令行用法见下方 [使用方法](#使用方法)。


## 使用方法

### GUI（推荐）

```powershell
run_gui_pro.bat
```
支持三种模式：粘贴抖音链接 / 选择本地文件 / 选择批量文件夹。

### 命令行

```powershell
# 抖音链接或分享文案
python main.py "https://www.douyin.com/video/VIDEO_ID"

# 本地音频
python main.py "D:\path\to\audio.mp3"

# 批量处理目录
python main.py "D:\path\to\media" --batch

# 指定输出目录
python main.py "audio.mp3" -o "D:\path\to\output"
```

### 独立文本清洗（无需音频）

```powershell
python text_cleaner.py input.txt
python text_cleaner.py input_folder --batch
```
Windows 下也可以直接把文件拖到 `run_text_cleaner.bat` 上。详细用法见 [README_text_cleaner.md](README_text_cleaner.md)。

### 中英双语字幕

```powershell
python make_bilingual_srt.py "D:\path\to\english_audio.mp3"
```

### 排错用命令

```powershell
python test_api_connection.py        # 测试大模型 API 是否连得通
python launcher.py --service-only    # 只检测/启动抖音解析服务，不开 GUI
python -m unittest discover -s tests -v   # 跑单元测试（不访问公网）
```

## 配置说明

`config.yaml` 由 `config.example.yaml` 复制而来，已加入 `.gitignore`，不会被提交——**不要把真实 API Key、Cookie 或私有地址写进 `config.example.yaml`**。

### 大模型 API

支持任意 OpenAI 兼容接口——云端（OpenAI、DeepSeek、硅基流动、Moonshot……）或本地部署（Ollama、LM Studio、vLLM）都可以，改一下 `base_url` / `api_key` / `model` 三项即可：

```yaml
siliconflow:
  api_key: "YOUR_API_KEY"      # 本地部署可随便填占位符
  base_url: "https://api.siliconflow.cn/v1"
  model: "Qwen/Qwen2.5-7B-Instruct"
  timeout: 900
  max_retries: 6
  concurrency: 16
```

<details>
<summary>抖音解析服务、Whisper、分块等完整配置项（点击展开）</summary>

**抖音解析服务**

```yaml
douyin_api:
  base_url: "http://127.0.0.1:8000"
  endpoint: "/api/hybrid/video_data"
  health_endpoint: "/health"
  health_timeout: 2
  timeout: 60
  trust_env: false          # 本地服务建议保持 false，避免系统代理拦截
  auto_start:
    enabled: true
    project_dir: "../Douyin_TikTok_Download_API"   # 抖音解析项目目录
    python: ".venv/Scripts/python.exe"              # 相对该目录的独立 Python
    command:
      - "{app_dir}/crawler_sidecar.py"   # {app_dir} 会自动替换为本项目目录
      - "--host"
      - "127.0.0.1"
      - "--port"
      - "8000"
      - "--max-attempts"
      - "5"
      - "--retry-delay"
      - "1"
    startup_timeout: 30
    poll_interval: 0.5
    stop_on_exit: false      # false = 关闭 GUI 后解析服务保持常驻，下次启动更快
    log_file: "./logs/douyin_api_service.log"
```

若 `base_url` 指向远程或 Docker 部署的服务，把 `auto_start.enabled` 设为 `false` 即可，启动器不会再尝试拉起本地进程。

**Whisper 语音识别**

```yaml
# GPU
whisper:
  model_size: "large-v3"
  device: "cuda"
  compute_type: "float16"
  language: null

# CPU（速度更慢，但不需要显卡）
whisper:
  model_size: "small"
  device: "cpu"
  compute_type: "int8"
  language: null
```

**其他参数**

```yaml
raw:
  include_timestamps: false

chunking:
  max_chars: 2500
  min_chars: 500

download:
  temp_dir: "./temp"
  output_dir: "./output"
  timeout: 120
  max_retries: 3
```




## 环境要求

- Python 3.10+
- NVIDIA GPU（推荐，用于加速语音识别；CPU 模式也能跑，速度较慢）
- 一个 OpenAI 兼容的大模型 API
- 处理抖音链接时，另需独立部署的 [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)

## 项目结构

<details>
<summary>点击展开完整文件说明</summary>

```
dy2md/
├── config.example.yaml       # 可提交的配置模板
├── config.yaml               # 本机配置（含密钥），已 gitignore
├── douyin_api_client.py      # 第三方解析服务 HTTP 适配器
├── service_manager.py        # 独立服务检测与进程管理
├── crawler_sidecar.py        # 在爬虫独立环境中运行的 HTTP Sidecar
├── launcher.py               # 一键启动入口
├── downloader.py             # 字段标准化与媒体下载
├── main.py                   # Pipeline / CLI 入口
├── gui_pro.py                # GUI
├── transcriber.py            # faster-whisper 语音识别
├── chunker.py                # 文本分块
├── cleaner.py                # LLM 文本清洗
├── translator.py             # 翻译模块
├── make_bilingual_srt.py     # 双语字幕生成
├── text_cleaner.py           # 独立文本清洗
├── test_api_connection.py    # LLM API 测试
├── tests/                    # HTTP 适配层单元测试
├── requirements.txt
├── setup.bat                 # 创建虚拟环境并安装依赖
├── run_gui_pro.bat
└── run_text_cleaner.bat
```

运行产生的 `temp/`、`output/`、`logs/`、模型缓存与下载到的音视频文件不会提交到 Git。

</details>

## 常见问题

**连不上抖音解析服务**
- 确认 `douyin_api.auto_start.enabled` 是否为 `true`，`project_dir` / `python` 路径是否存在
- 浏览器打开对应端口的 `/health` 或 `/docs` 看能不能访问
- 本地服务建议保持 `trust_env: false`，避免系统代理干扰
- 查看 `logs/douyin_api_service.log`

**解析结果里没有音频/视频地址**
第三方接口字段、Cookie 或抖音接口本身可能变了。先在 Sidecar 的 `/docs` 里手动调用一次接口，对照 `logs/douyin_api_service.log` 里的原始报错排查。

**LLM 请求失败**
- 检查 `siliconflow.base_url` / `api_key` / `model`
- 本地模型服务先确认进程真的在监听
- 云端服务如需代理，设置 `HTTP_PROXY` / `HTTPS_PROXY`

## 免责声明

本项目仅用于个人学习和研究用途。抖音解析能力依赖第三方开源项目，请遵守抖音的用户协议、相关法律法规以及内容原作者的权益，不要用于批量爬取、商业分发或侵犯他人版权的场景。因使用本项目产生的任何后果由使用者自行承担。

## 致谢

- 抖音 / TikTok 解析能力由 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) 提供
- 语音识别基于 [faster-whisper]

## License

[MIT](LICENSE)
