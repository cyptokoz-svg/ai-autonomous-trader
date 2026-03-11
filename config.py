"""
AI 自主交易员 — 全局配置
"""
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# ── 交易对 ──
PAIRS = [
    "BTC-USDT-SWAP",
    "ETH-USDT-SWAP",
]

# ── OKX API ──
OKX_BASE_URL = "https://www.okx.com"

# 从 ~/.okx/config.toml 读取 credentials
def _load_okx_config() -> dict:
    p = Path.home() / ".okx" / "config.toml"
    if not p.exists():
        return {}
    with open(p, "rb") as f:
        return tomllib.load(f)

_OKX_CFG = _load_okx_config()
_DEFAULT_PROFILE = _OKX_CFG.get("default_profile", "demo")

def get_credentials(profile: str | None = None) -> dict:
    """获取指定 profile 的 API credentials"""
    name = profile or _DEFAULT_PROFILE
    return _OKX_CFG.get("profiles", {}).get(name, {})

# 默认 profile
_CREDS = get_credentials()
OKX_API_KEY = _CREDS.get("api_key", "")
OKX_SECRET_KEY = _CREDS.get("secret_key", "")
OKX_PASSPHRASE = _CREDS.get("passphrase", "")
OKX_DEMO = _CREDS.get("demo", True)

# ── 时间框架 ──
# 按 prompt 决策流程: 日线(大方向) → 4H(中期) → 1H/15m(入场)
TIMEFRAMES = {
    "15m": {"bar": "15m", "count": 192, "refresh_sec": 60},
    "1H":  {"bar": "1H",  "count": 300, "refresh_sec": 300},
    "4H":  {"bar": "4H",  "count": 180, "refresh_sec": 300},
    "1D":  {"bar": "1D",  "count": 365, "refresh_sec": 1800},
}

# ── EMA 参数 (prompt 定义: 7/25/99) ──
EMA_PERIODS = [7, 25, 99]
