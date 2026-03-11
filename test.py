import httpx
from openai import OpenAI

# 1. 显式禁用系统环境变量（trust_env=False 会忽略 http_proxy 等变量）
# 2. 使用正确的 httpx 客户端配置
http_client = httpx.Client(trust_env=False)

client = OpenAI(
    api_key="sk-1e74cd6675a6404b9811ee09fc49a50d", 
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    http_client=http_client
)

try:
    print("🚀 正在发起原生 API 请求测试...")
    response = client.chat.completions.create(
        model="qwen-plus",
        messages=[{"role": "user", "content": "你好，请确认你是否收到了这条消息。"}]
    )
    print("✅ 请求成功！")
    print(f"🤖 Qwen 响应：{response.choices[0].message.content}")
except Exception as e:
    print("\n❌ 请求仍然失败！")
    print(f"错误类型：{type(e).__name__}")
    print(f"错误细节：{e}")