"""
AI 自主交易员 — 大模型 API 配置
支持多家模型供应商，统一调用接口

配置方式：在 ~/.okx/config.toml 中添加 [ai] 段
"""
import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


# ── 支持的模型供应商 ──

PROVIDERS = {
    "anthropic": {
        "name": "Anthropic (Claude)",
        "base_url": "https://api.anthropic.com/v1/messages",
        "models": [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ],
        "default_model": "claude-sonnet-4-6",
        "env_key": "ANTHROPIC_API_KEY",
        "headers": lambda key: {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    },
    "openai": {
        "name": "OpenAI (GPT)",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "o3-mini",
        ],
        "default_model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
        "headers": lambda key: {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
    },
    "google": {
        "name": "Google (Gemini)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "models": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
        ],
        "default_model": "gemini-2.5-flash",
        "env_key": "GOOGLE_API_KEY",
        "headers": lambda key: {
            "content-type": "application/json",
        },
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        "default_model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "headers": lambda key: {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
    },
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ],
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
        "headers": lambda key: {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
    },
    "openrouter": {
        "name": "OpenRouter (多模型聚合)",
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "models": [
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o",
            "google/gemini-2.5-pro",
            "deepseek/deepseek-chat-v3",
            "meta-llama/llama-3.3-70b-instruct",
        ],
        "default_model": "anthropic/claude-sonnet-4",
        "env_key": "OPENROUTER_API_KEY",
        "headers": lambda key: {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
    },
    "xai": {
        "name": "xAI (Grok)",
        "base_url": "https://api.x.ai/v1/chat/completions",
        "models": [
            "grok-3",
            "grok-3-mini",
        ],
        "default_model": "grok-3-mini",
        "env_key": "XAI_API_KEY",
        "headers": lambda key: {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
    },
}


# ── 加载配置 ──

def _load_ai_config() -> dict:
    """从 ~/.okx/config.toml 的 [ai] 段读取配置"""
    p = Path.home() / ".okx" / "config.toml"
    if not p.exists():
        return {}
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    return cfg.get("ai", {})


_AI_CFG = _load_ai_config()


def get_provider() -> str:
    """获取当前 AI 供应商"""
    return _AI_CFG.get("provider", os.environ.get("AI_PROVIDER", "anthropic"))


def get_model() -> str:
    """获取当前模型"""
    provider = get_provider()
    default = PROVIDERS.get(provider, {}).get("default_model", "")
    return _AI_CFG.get("model", os.environ.get("AI_MODEL", default))


def get_api_key() -> str:
    """获取 API Key（优先 config.toml，其次环境变量）"""
    key = _AI_CFG.get("api_key", "")
    if key:
        return key
    provider = get_provider()
    env_key = PROVIDERS.get(provider, {}).get("env_key", "")
    return os.environ.get(env_key, "")


def get_base_url() -> str:
    """获取 API Base URL（支持自定义）"""
    custom = _AI_CFG.get("base_url", "")
    if custom:
        return custom
    provider = get_provider()
    return PROVIDERS.get(provider, {}).get("base_url", "")


def get_headers() -> dict:
    """获取请求头"""
    provider = get_provider()
    key = get_api_key()
    header_fn = PROVIDERS.get(provider, {}).get("headers")
    if header_fn:
        return header_fn(key)
    return {"Authorization": f"Bearer {key}", "content-type": "application/json"}


def get_config_summary() -> dict:
    """返回当前配置摘要（不含 API Key）"""
    provider = get_provider()
    info = PROVIDERS.get(provider, {})
    return {
        "provider": provider,
        "provider_name": info.get("name", provider),
        "model": get_model(),
        "base_url": get_base_url(),
        "has_key": bool(get_api_key()),
        "available_models": info.get("models", []),
    }


# ── 打印配置 ──

if __name__ == "__main__":
    import json
    summary = get_config_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print()
    print("所有支持的供应商:")
    for pid, info in PROVIDERS.items():
        key_set = "✓" if os.environ.get(info["env_key"], "") else "✗"
        print(f"  {pid:12s} — {info['name']:30s} [{key_set} {info['env_key']}]")
