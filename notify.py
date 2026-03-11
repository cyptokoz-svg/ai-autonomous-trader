"""Telegram notification module for autonomous trader."""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

CST = timezone(timedelta(hours=8))


def send_message(text: str) -> bool:
    """Send a message via Telegram bot. Returns True on success, False otherwise."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ts() -> str:
    return datetime.now(CST).strftime("%H:%M:%S")


def notify_open(coin: str, side: str, entry_price: float, leverage: int, sheets: float):
    emoji = "\U0001f4c8" if side.upper() == "LONG" else "\U0001f4c9"
    text = (
        f"{emoji} <b>Open {side.upper()}</b> {coin}\n"
        f"Entry: {entry_price}  |  Lev: {leverage}x  |  Size: {sheets}\n"
        f"Time: {_ts()}"
    )
    send_message(text)


def notify_close(coin: str, side: str, pnl: float, close_reason: str):
    emoji = "\U0001f4b0" if pnl >= 0 else "\U0001f4b8"
    pnl_str = f"+{pnl:.2f}" if pnl >= 0 else f"{pnl:.2f}"
    text = (
        f"{emoji} <b>Close {side.upper()}</b> {coin}\n"
        f"PnL: {pnl_str} USDT  |  Reason: {close_reason}\n"
        f"Time: {_ts()}"
    )
    send_message(text)


def notify_error(error_msg: str):
    text = f"\u274c <b>Error</b>\n{error_msg}\nTime: {_ts()}"
    send_message(text)


def notify_round(action: str, summary: str):
    """Notify on each decision round. Skips HOLD to avoid spam."""
    if action.upper() == "HOLD":
        return
    text = f"\U0001f501 <b>{action.upper()}</b>\n{summary}\nTime: {_ts()}"
    send_message(text)
