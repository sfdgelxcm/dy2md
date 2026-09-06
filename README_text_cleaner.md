# 独立文本清洗工具

## 功能说明

这是一个独立的文本清洗工具，可以直接处理未清洗的文稿或文本文件，无需经过音频转写流程。

## 使用方法

### 1. 清洗单个文本文件

```bash
python text_cleaner.py input.txt
```

或指定输出路径：
```bash
python text_cleaner.py input.txt -o output.md
```

### 2. 批量清洗多个文本文件

```bash
python text_cleaner.py file1.txt file2.md file3.text
```

### 3. 批量清洗文件夹

```bash
python text_cleaner.py 文件夹路径 --batch
```

支持的文件格式：`.txt`, `.md`, `.text`

### 4. 直接清洗文本

```bash
python text_cleaner.py "你的文本内容" --text
```

### 5. 使用批处理文件（Windows）

直接拖拽文件或文件夹到 `run_text_cleaner.bat` 上即可。

## 清洗效果

工具会自动：
- 添加正确的标点符号和段落分隔
- 删除口语化表达（如"嗯"、"啊"、"那个"、"就是说"等）
- 修正明显的语音识别错误和错别字
- 保持原意，不添加或删除实质内容
- 使文本结构清晰、易于阅读

## 配置

### 基础配置

在 `config.yaml` 中配置：
- `siliconflow.api_key`: 硅基流动API密钥
- `chunking.max_chars`: 每块最大字符数（默认2500）

### 代理配置（如需要）

如果你的网络环境需要代理才能访问API，有两种配置方式：

**方式1：系统环境变量（推荐）**
```bash
# Windows CMD
set HTTP_PROXY=http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890

# Windows PowerShell
$env:HTTP_PROXY="http://127.0.0.1:7890"
$env:HTTPS_PROXY="http://127.0.0.1:7890"
```

**方式2：修改代码**

编辑 `cleaner.py`，在 `Cleaner` 类的 `__init__` 方法中取消注释代理配置：
```python
self.proxies = {
    "http://": "http://127.0.0.1:7890",
    "https://": "http://127.0.0.1:7890"
}
```

### 测试API连接

运行以下命令测试API连接是否正常：
```bash
python test_api_connection.py
```

## 输出

清洗后的文件默认保存在 `./output` 目录，文件名为 `原文件名_cleaned.md`

## 常见问题

### 连接错误（ConnectError）

如果遇到 `httpx.ConnectError` 错误，可能是：
1. 网络连接问题 - 检查网络是否正常
2. 需要配置代理 - 参考上面的代理配置说明
3. 防火墙阻止 - 检查防火墙设置

### API密钥错误

确保在 `config.yaml` 中正确配置了硅基流动的API密钥。
