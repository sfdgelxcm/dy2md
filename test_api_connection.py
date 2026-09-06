"""
测试 OpenAI 兼容 API 连接
"""
import asyncio
import httpx
import yaml

async def test_connection():
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    api_key = config['siliconflow']['api_key']
    base_url = config['siliconflow']['base_url']
    model = config['siliconflow']['model']
    reasoning_effort = str(config['siliconflow'].get('reasoning_effort', '') or '').strip()
    
    print(f"测试连接到: {base_url}")
    print(f"使用模型: {model}")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "你好"}
        ],
        "max_tokens": 10,
        "stream": False,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            print("\n正在发送请求...")
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            print("[OK] 连接成功!")
            print(f"响应: {result['choices'][0]['message']['content']}")
            return True
    except httpx.ConnectError as e:
        print("[X] 连接失败: 无法连接到服务器")
        print(f"  错误: {e}")
        print("\n可能的原因:")
        print("  1. 网络连接问题")
        print("  2. 需要配置代理")
        print("  3. 防火墙阻止了连接")
        print("\n解决方案:")
        print("  - 检查网络连接")
        print("  - 如需代理，请在系统环境变量中设置 HTTP_PROXY 和 HTTPS_PROXY")
        print("  - 或者在代码中配置代理（见 cleaner.py）")
        return False
    except httpx.HTTPStatusError as e:
        print(f"[X] API错误: {e.response.status_code}")
        print(f"  响应: {e.response.text}")
        return False
    except Exception as e:
        print(f"[X] 未知错误: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())
