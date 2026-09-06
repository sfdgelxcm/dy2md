# Video to Markdown

抖音视频 / 本地音视频转 Markdown 的 ETL 工具：媒体获取 → 语音识别 → AI 清洗 → 输出结构化 Markdown。

## 功能特性

- **抖音视频转写**：输入抖音链接或分享文案，通过独立解析服务获取媒体地址
- **本地音视频转写**：支持 mp3 / wav / m4a / flac / ogg / mp4
- **批量处理**：处理整个目录或一次选择多个文件
- **AI 文本清洗**：添加标点、修正错字、整理口语和段落
- **智能文件名**：根据内容生成简洁文件名
- **双语字幕**：将英文音视频转换为中英双语 SRT
- **独立文本清洗**：无需音频，直接清洗 txt / md 文稿
- **GUI 与 CLI**：提供 Windows 图形界面及命令行入口

## 处理流程

```text
抖音链接 ──HTTP──> crawler_sidecar.py（爬虫独立环境）
                         │
                         ▼
本地音视频 ─────────> 媒体文件
                         │
                         ▼
                   faster-whisper
                         │
                         ▼
                  分块与 LLM 清洗
                         │
                         ▼
                      Markdown
```

## 架构：解析服务与转写应用完全解耦

本项目不包含抖音爬虫，也不会把爬虫项目加入 `sys.path`。两套程序分别安装、使用各自的虚拟环境，仅通过 HTTP API 通信；一键启动器只负责拉起独立进程，不会导入对方代码：

```text
┌──────────────────────────┐       HTTP / JSON       ┌──────────────────────────────┐
│ video_to_markdown         │ ──────────────────────> │ crawler_sidecar.py            │
│ 独立 .venv                │ <────────────────────── │ 独立 .venv / Docker           │
│ ASR、LLM、GUI、Markdown   │                         │ 链接解析与 Cookie 管理         │
└──────────────────────────┘                         └──────────────────────────────┘
```

代码边界如下：

- `douyin_api_client.py`：只负责调用第三方解析服务并校验 HTTP/JSON 响应
- `downloader.py`：把第三方字段转换成本项目的统一结构，并下载媒体
- `service_manager.py`：检测服务状态，必要时用爬虫自己的 Python 后台启动服务
- `crawler_sidecar.py`：在爬虫独立环境中运行，只暴露本项目需要的稳定 HTTP 接口
- `launcher.py`：先确保服务就绪，再打开 GUI
- `main.py`、`gui_pro.py`：只依赖本项目的下载接口，不了解爬虫实现
- 直接使用 CLI 处理本地音视频或文本时，不需要抖音解析服务

因此两边可以独立升级、独立部署，也可以把解析服务放在另一台机器或容器中。

## 环境要求

- Python 3.10+
- NVIDIA GPU（推荐）；CPU 模式也可运行
- OpenAI 兼容的大模型 API
- 处理抖音链接时，另需独立运行的 [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)

## 安装本项目

本项目必须使用自己的虚拟环境：

Windows 用户可以直接双击 `setup.bat`。也可以手动执行：

```powershell
git clone <本仓库地址>
cd video_to_markdown

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item config.example.yaml config.yaml
```

如果只处理本地文件，可以不部署抖音解析服务。

## 配置

### 抖音解析服务

```yaml
douyin_api:
  base_url: "http://127.0.0.1:8000"
  endpoint: "/api/hybrid/video_data"
  health_endpoint: "/health"
  health_timeout: 2
  timeout: 60
  trust_env: false
  auto_start:
    enabled: true
    project_dir: "../Douyin_TikTok_Download_API"
    python: ".venv/Scripts/python.exe"
    command:
      - "{app_dir}/crawler_sidecar.py"
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
    stop_on_exit: false
    log_file: "./logs/douyin_api_service.log"
```

- `base_url`：解析服务地址，可使用本机、局域网或远程地址
- `endpoint`：当前适配的混合视频解析接口
- `health_endpoint`：启动器用来判断服务是否就绪的地址
- `timeout`：解析请求超时时间，单位为秒
- `trust_env`：是否读取系统代理变量；本地服务通常设为 `false`
- `auto_start.project_dir`：爬虫项目目录；可以是相对路径或本机绝对路径
- `auto_start.python`：相对于爬虫目录的独立 Python 路径
- `auto_start.command`：交给爬虫 Python 执行的启动参数，不经过 Shell
- `{app_dir}`：启动时自动替换为本项目目录，不需要手工填写
- `--max-attempts`：遇到抖音临时 403 等解析失败时，由 Sidecar 自动重新生成请求并重试
- `stop_on_exit: false`：关闭 GUI 后让解析服务保持常驻，下次启动更快

### 大模型 API

`siliconflow` 是历史配置段名称，实际支持任意 OpenAI 兼容接口：

```yaml
siliconflow:
  api_key: "YOUR_API_KEY"
  base_url: "https://api.siliconflow.cn/v1"
  model: "Qwen/Qwen2.5-7B-Instruct"
  reasoning_effort: ""
  timeout: 900
  max_retries: 6
  retry_base_delay: 5
  retry_max_delay: 90
  concurrency: 16
```

### Whisper 与输出

GPU 示例：

```yaml
whisper:
  model_size: "large-v3"
  device: "cuda"
  compute_type: "float16"
  language: null
```

CPU 示例：

```yaml
whisper:
  model_size: "small"
  device: "cpu"
  compute_type: "int8"
  language: null
```

其他参数：

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

`config.yaml` 已加入 `.gitignore`。不要把真实 API Key、Cookie 或私有服务地址写入 `config.example.yaml`。

## 安装 Douyin_TikTok_Download_API 依赖项目

以下操作在另一个目录和另一个终端中完成：

```powershell
git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API.git
cd Douyin_TikTok_Download_API

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

根据该项目文档配置 Cookie。正常使用不需要手动启动它；启动器会使用这个项目的独立 Python 运行 `crawler_sidecar.py`。

如需排错，可在本项目目录手动执行：

```powershell
<爬虫项目目录>\.venv\Scripts\python.exe crawler_sidecar.py --host 127.0.0.1 --port 8000
```

Sidecar 启动后，接口文档位于：

```text
http://127.0.0.1:8000/docs
```

正常使用时，`launcher.py` 会自动执行 `auto_start.command`，等待 `/health` 就绪后再打开 GUI，不需要修改第三方项目自身的默认端口。

启动器只管理独立进程，不共享环境、不修改第三方代码。若 `base_url` 指向远程或 Docker 服务，可将 `auto_start.enabled` 设为 `false`。

## 使用方法

### GUI

完成一次路径配置后，直接双击：

```text
run_gui_pro.bat
```

它会自动检测服务；服务未运行时，会使用爬虫自己的 `.venv` 静默启动并等待就绪，然后打开 GUI。也可以执行：

```powershell
python launcher.py
```

如需绕过服务管理、只打开 GUI，可直接运行 `python gui_pro.py`。

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

### 独立文本清洗

```powershell
python text_cleaner.py input.txt
python text_cleaner.py input.txt -o output.md
python text_cleaner.py input_folder --batch
```

Windows 下也可把文本文件拖到 `run_text_cleaner.bat`。详细说明见 [README_text_cleaner.md](README_text_cleaner.md)。

### 中英双语字幕

```powershell
python make_bilingual_srt.py "D:\path\to\english_audio.mp3"
```

### API 连通性测试

```powershell
# 测试 OpenAI 兼容大模型接口
python test_api_connection.py

# 只检测/启动抖音解析服务，不打开 GUI
python launcher.py --service-only

# 运行不访问公网的抖音适配层单元测试
python -m unittest discover -s tests -v
```

## 项目结构

```text
video_to_markdown/
├── config.example.yaml       # 可提交的配置模板
├── config.yaml               # 本机配置，已被 gitignore
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
├── setup.bat                 # 创建本项目独立环境并安装依赖
├── run_gui_pro.bat
└── run_text_cleaner.bat
```

运行产生的 `temp/`、`output/`、`logs/`、模型缓存和音视频文件不会提交到 Git。

## 常见问题

### 无法连接抖音解析服务

- 检查 `auto_start.enabled` 是否为 `true`
- 检查 `auto_start.project_dir` 和 `auto_start.python` 是否存在
- 确认浏览器可以打开对应端口的 `/health` 或 `/docs`
- 检查 `douyin_api.base_url` 和 `douyin_api.endpoint`
- 如果调用本机服务，建议保持 `trust_env: false`，避免系统代理拦截本地请求
- 查看 `logs/douyin_api_service.log` 中的第三方服务启动日志

### 响应中没有音频或视频地址

第三方接口字段、Cookie 或抖音接口可能发生变化。先在 Sidecar 的 `/docs` 中调用 `/api/hybrid/video_data`，并查看 `logs/douyin_api_service.log` 中的原始异常。

### LLM 请求失败

- 检查 `siliconflow.base_url`、`api_key` 和 `model`
- 本地模型服务需先确认其进程正在监听
- 云端服务如需代理，可设置 `HTTP_PROXY` / `HTTPS_PROXY`

## 致谢

- 抖音 / TikTok 解析能力由 [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) 提供
- 语音识别基于 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

## License

项目目前未附带开源协议；公开发布前可根据需要添加 `LICENSE`。
