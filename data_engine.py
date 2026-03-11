"""
AI 自主交易员 — 数据引擎
拉取 OKX 行情 + 计算技术指标 + 生成标准化报告

改造自策略工厂 data_engine.py, 精简为 BTC/ETH 双币
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp
import pandas as pd
import pandas_ta as ta

from config import PAIRS, TIMEFRAMES, OKX_BASE_URL, EMA_PERIODS, OKX_DEMO

logger = logging.getLogger("data_engine")


class DataEngine:
    """
    维护 BTC/ETH 的多时间框架 OHLCV + 指标,
    以及 funding rate / open interest / ticker / orderbook 信息.
    """

    def __init__(self):
        self.pairs = PAIRS
        self.timeframes = TIMEFRAMES
        self.base_url = OKX_BASE_URL

        # pair -> tf -> pd.DataFrame
        self._candles: dict[str, dict[str, pd.DataFrame]] = {p: {} for p in self.pairs}
        self._last_ts: dict[str, dict[str, int]] = {p: {} for p in self.pairs}
        self._last_refresh: dict[str, dict[str, float]] = {p: {} for p in self.pairs}

        # 合约数据
        self._funding: dict[str, dict] = {}
        self._oi: dict[str, float] = {}
        self._ticker: dict[str, dict] = {}
        self._orderbook: dict[str, dict] = {}
        self._long_short_ratio: dict[str, dict] = {}

        self._initialized = False

    # ──────────────────── 公开接口 ────────────────────

    def get_df(self, pair: str, tf: str) -> pd.DataFrame | None:
        return self._candles.get(pair, {}).get(tf)

    def get_ticker(self, pair: str) -> dict:
        return self._ticker.get(pair, {})

    def get_funding(self, pair: str) -> dict:
        return self._funding.get(pair, {})

    def get_oi(self, pair: str) -> float:
        return self._oi.get(pair, 0.0)

    def get_orderbook(self, pair: str) -> dict:
        return self._orderbook.get(pair, {})

    # ──────────────────── 主更新 ────────────────────

    async def update(self):
        """主更新入口, 由外部调用."""
        now = time.time()
        try:
            headers = {"x-simulated-trading": "1"} if OKX_DEMO else {}
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers,
            ) as session:
                tasks: list[asyncio.Task] = []

                for pair in self.pairs:
                    tasks.append(asyncio.ensure_future(self._safe_fetch_funding(session, pair)))
                    tasks.append(asyncio.ensure_future(self._safe_fetch_oi(session, pair)))
                    tasks.append(asyncio.ensure_future(self._safe_fetch_ticker(session, pair)))
                    tasks.append(asyncio.ensure_future(self._safe_fetch_orderbook(session, pair)))
                    tasks.append(asyncio.ensure_future(self._safe_fetch_long_short_ratio(session, pair)))

                    for tf, tf_cfg in self.timeframes.items():
                        last = self._last_refresh.get(pair, {}).get(tf, 0)
                        if now - last >= tf_cfg["refresh_sec"]:
                            tasks.append(asyncio.ensure_future(
                                self._safe_update_candles(session, pair, tf, tf_cfg)
                            ))

                if tasks:
                    await asyncio.gather(*tasks)

            if not self._initialized:
                self._initialized = True
                logger.info("DataEngine 初始化完成 — %d 对, %d 时间框架",
                            len(self.pairs), len(self.timeframes))

        except Exception as e:
            logger.error("DataEngine.update 异常: %s", e, exc_info=True)

    # ──────────────────── K 线 ────────────────────

    async def fetch_candles(
        self, session: aiohttp.ClientSession, pair: str, tf: str, limit: int = 300,
    ) -> pd.DataFrame:
        url = f"{self.base_url}/api/v5/market/candles"
        params = {"instId": pair, "bar": tf, "limit": str(limit)}

        async with session.get(url, params=params) as resp:
            data = await resp.json()

        if data.get("code") != "0" or not data.get("data"):
            logger.warning("fetch_candles 失败 %s/%s: %s", pair, tf, data.get("msg", "empty"))
            return pd.DataFrame()

        rows = data["data"]
        df = pd.DataFrame(rows, columns=[
            "ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"
        ])
        df["ts"] = pd.to_numeric(df["ts"])
        for col in ["open", "high", "low", "close", "vol", "volCcy", "volCcyQuote"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["confirm"] = df["confirm"].astype(str)
        df = df.sort_values("ts").reset_index(drop=True)
        df["datetime"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df

    async def _safe_update_candles(self, session, pair, tf, tf_cfg):
        try:
            existing = self._candles.get(pair, {}).get(tf)
            last_ts = self._last_ts.get(pair, {}).get(tf)

            if existing is not None and not existing.empty and last_ts:
                new_df = await self.fetch_candles(session, pair, tf, limit=50)
                if new_df.empty:
                    return
                combined = pd.concat([existing, new_df], ignore_index=True)
                combined = combined.drop_duplicates(subset="ts", keep="last")
                combined = combined.sort_values("ts").reset_index(drop=True)
                max_rows = tf_cfg["count"] + 100
                if len(combined) > max_rows:
                    combined = combined.tail(max_rows).reset_index(drop=True)
                df = combined
            else:
                df = await self.fetch_candles(session, pair, tf, limit=tf_cfg["count"])
                if df.empty:
                    return

            base_cols = ["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm", "datetime"]
            df = df[[c for c in base_cols if c in df.columns]].copy()
            df = self.compute_indicators(df)

            self._candles.setdefault(pair, {})[tf] = df
            self._last_ts.setdefault(pair, {})[tf] = int(df["ts"].iloc[-1])
            self._last_refresh.setdefault(pair, {})[tf] = time.time()

            logger.debug("更新 K 线 %s/%s: %d 行", pair, tf, len(df))

        except Exception as e:
            logger.error("_safe_update_candles %s/%s 异常: %s", pair, tf, e, exc_info=True)

    # ──────────────────── 技术指标 ────────────────────

    @staticmethod
    def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标, AI 交易员 prompt 定义的核心指标 + 扩展指标.
        AI 自己选择使用哪些.
        """
        if df.empty or len(df) < 50:
            return df

        h, l, c, v = df["high"], df["low"], df["close"], df["vol"]

        # ── 趋势 (Trend) ──

        # EMA — prompt 核心: 7/25/99
        for p in EMA_PERIODS:
            df[f"ema{p}"] = ta.ema(c, length=p)

        # SMA 补充
        df["sma50"] = ta.sma(c, length=50)
        df["sma200"] = ta.sma(c, length=200)

        # MACD
        macd = ta.macd(c, fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            for col in macd.columns:
                df[col] = macd[col]

        # SuperTrend
        st = ta.supertrend(h, l, c, length=14, multiplier=3.0)
        if st is not None and not st.empty:
            for col in st.columns:
                df[col] = st[col]

        # ADX
        adx = ta.adx(h, l, c, length=14)
        if adx is not None and not adx.empty:
            for col in adx.columns:
                df[col] = adx[col]

        # ── 动量 (Momentum) ──

        # RSI — prompt 核心: 14
        df["rsi14"] = ta.rsi(c, length=14)

        # Stochastic
        stoch = ta.stoch(h, l, c, k=14, d=3, smooth_k=3)
        if stoch is not None and not stoch.empty:
            for col in stoch.columns:
                df[col] = stoch[col]

        # MFI
        df["mfi14"] = ta.mfi(h, l, c, v, length=14)

        # ── 波动 (Volatility) ──

        # ATR — prompt 核心: 14
        df["atr14"] = ta.atr(h, l, c, length=14)

        # 布林带
        bb = ta.bbands(c, length=20, std=2.0)
        if bb is not None and not bb.empty:
            bb.columns = [col.replace("_2.0_2.0", "_2.0") for col in bb.columns]
            for col in bb.columns:
                df[col] = bb[col]

        # ── 量价 (Volume) ──

        # OBV
        df["obv"] = ta.obv(c, v)

        # Volume SMA
        df["vol_sma20"] = ta.sma(v, length=20)

        # 量比 (当前成交量 / 20日均量)
        df["vol_ratio"] = v / df["vol_sma20"].replace(0, pd.NA)

        # ── Donchian Channel ──
        dc = ta.donchian(h, l, lower_length=20, upper_length=20)
        if dc is not None and not dc.empty:
            for col in dc.columns:
                df[col] = dc[col]

        # ── VWAP (按日重置) ──
        if "datetime" in df.columns:
            typical = (h + l + c) / 3
            tp_vol = typical * v
            day_group = df["datetime"].dt.date
            df["vwap"] = tp_vol.groupby(day_group).cumsum() / v.groupby(day_group).cumsum()
        else:
            typical = (h + l + c) / 3
            df["vwap"] = (typical * v).cumsum() / v.cumsum()

        # ── CMF (Chaikin Money Flow, 20期) ──
        mfv = ((c - l) - (h - c)) / (h - l + 1e-10) * v
        df["cmf20"] = mfv.rolling(20).sum() / (v.rolling(20).sum() + 1e-10)

        # ── Pivot Points (基于前一日 HLC) ──
        if "datetime" in df.columns:
            day_group = df["datetime"].dt.date
            daily_agg = df.groupby(day_group).agg(
                dh=("high", "max"), dl=("low", "min"), dc=("close", "last")
            ).shift(1)
            prev_h = day_group.map(daily_agg["dh"])
            prev_l = day_group.map(daily_agg["dl"])
            prev_c = day_group.map(daily_agg["dc"])
            pp = (prev_h + prev_l + prev_c) / 3
            df["pivot"] = pp
            df["pivot_r1"] = 2 * pp - prev_l
            df["pivot_s1"] = 2 * pp - prev_h
        else:
            pp = (h.shift(1) + l.shift(1) + c.shift(1)) / 3
            df["pivot"] = pp
            df["pivot_r1"] = 2 * pp - l.shift(1)
            df["pivot_s1"] = 2 * pp - h.shift(1)

        # ── ROC (Rate of Change, 12期) ──
        df["roc12"] = ta.roc(c, length=12)

        return df

    # ──────────────────── Funding Rate ────────────────────

    async def fetch_funding_rate(self, session: aiohttp.ClientSession, pair: str) -> dict:
        result: dict[str, Any] = {}

        url = f"{self.base_url}/api/v5/public/funding-rate"
        params = {"instId": pair}
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        if data.get("code") == "0" and data.get("data"):
            item = data["data"][0]
            result["current_rate"] = float(item.get("fundingRate") or 0)
            result["next_rate"] = float(item.get("nextFundingRate") or 0)
            result["funding_time"] = int(item.get("fundingTime") or 0)

        url_hist = f"{self.base_url}/api/v5/public/funding-rate-history"
        params_hist = {"instId": pair, "limit": "30"}
        async with session.get(url_hist, params=params_hist) as resp2:
            data2 = await resp2.json()
        if data2.get("code") == "0" and data2.get("data"):
            rates = [float(r.get("fundingRate", 0)) for r in data2["data"]]
            result["history"] = rates
            result["avg_rate"] = sum(rates) / len(rates) if rates else 0.0

            # 趋势: 取最近5期 (history 按时间倒序, 反转后从旧到新)
            recent_5 = list(reversed(rates[:5])) if len(rates) >= 5 else list(reversed(rates))
            if len(recent_5) >= 2:
                diffs = [recent_5[i+1] - recent_5[i] for i in range(len(recent_5) - 1)]
                rising = sum(1 for d in diffs if d > 0)
                falling = sum(1 for d in diffs if d < 0)
                if rising > falling:
                    result["trend"] = "rising"
                elif falling > rising:
                    result["trend"] = "falling"
                else:
                    result["trend"] = "flat"
            else:
                result["trend"] = "flat"

        return result

    async def _safe_fetch_funding(self, session, pair):
        try:
            self._funding[pair] = await self.fetch_funding_rate(session, pair)
        except Exception as e:
            logger.error("fetch_funding %s 异常: %s", pair, e)

    # ──────────────────── Long/Short Ratio ────────────────────

    async def fetch_long_short_ratio(self, session: aiohttp.ClientSession, pair: str) -> dict:
        """获取多空持仓人数比（用 ccy 参数，如 BTC）."""
        url = f"{self.base_url}/api/v5/rubik/stat/contracts/long-short-account-ratio"
        ccy = pair.split("-")[0]  # BTC-USDT-SWAP -> BTC
        params = {"ccy": ccy, "period": "1H"}
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        if data.get("code") == "0" and data.get("data") and len(data["data"]) > 0:
            latest = data["data"][0]
            ratio = float(latest[1]) if len(latest) > 1 else 1.0
            # ratio > 1 表示多头人数多，< 1 表示空头人数多
            return {
                "ratio": ratio,
                "period": "1H",
            }
        return {}

    async def _safe_fetch_long_short_ratio(self, session, pair):
        try:
            self._long_short_ratio[pair] = await self.fetch_long_short_ratio(session, pair)
        except Exception as e:
            logger.error("fetch_long_short_ratio %s 异常: %s", pair, e)

    # ──────────────────── Open Interest ────────────────────

    async def fetch_oi(self, session: aiohttp.ClientSession, pair: str) -> float:
        url = f"{self.base_url}/api/v5/public/open-interest"
        params = {"instType": "SWAP", "instId": pair}
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        if data.get("code") == "0" and data.get("data"):
            return float(data["data"][0].get("oi", 0))
        return 0.0

    async def _safe_fetch_oi(self, session, pair):
        try:
            self._oi[pair] = await self.fetch_oi(session, pair)
        except Exception as e:
            logger.error("fetch_oi %s 异常: %s", pair, e)

    # ──────────────────── Ticker ────────────────────

    async def fetch_ticker(self, session: aiohttp.ClientSession, pair: str) -> dict:
        url = f"{self.base_url}/api/v5/market/ticker"
        params = {"instId": pair}
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        if data.get("code") == "0" and data.get("data"):
            t = data["data"][0]
            return {
                "last": float(t.get("last", 0)),
                "bid": float(t.get("bidPx", 0)),
                "ask": float(t.get("askPx", 0)),
                "bid_sz": float(t.get("bidSz", 0)),
                "ask_sz": float(t.get("askSz", 0)),
                "vol24h": float(t.get("vol24h", 0)),
                "volCcy24h": float(t.get("volCcy24h", 0)),
                "high24h": float(t.get("high24h", 0)),
                "low24h": float(t.get("low24h", 0)),
                "open24h": float(t.get("open24h", 0)),
                "ts": int(t.get("ts", 0)),
            }
        return {}

    async def _safe_fetch_ticker(self, session, pair):
        try:
            self._ticker[pair] = await self.fetch_ticker(session, pair)
        except Exception as e:
            logger.error("fetch_ticker %s 异常: %s", pair, e)

    # ──────────────────── Orderbook ────────────────────

    async def fetch_orderbook(self, session: aiohttp.ClientSession, pair: str, depth: int = 5) -> dict:
        url = f"{self.base_url}/api/v5/market/books"
        params = {"instId": pair, "sz": str(depth)}
        async with session.get(url, params=params) as resp:
            data = await resp.json()
        if data.get("code") == "0" and data.get("data"):
            book = data["data"][0]
            bids = [[float(x[0]), float(x[1])] for x in book.get("bids", [])]
            asks = [[float(x[0]), float(x[1])] for x in book.get("asks", [])]
            total_bid = sum(b[1] for b in bids)
            total_ask = sum(a[1] for a in asks)
            return {
                "bids": bids,
                "asks": asks,
                "total_bid_sz": total_bid,
                "total_ask_sz": total_ask,
                "bid_ask_ratio": round(total_bid / total_ask, 3) if total_ask > 0 else 0,
            }
        return {}

    async def _safe_fetch_orderbook(self, session, pair):
        try:
            self._orderbook[pair] = await self.fetch_orderbook(session, pair)
        except Exception as e:
            logger.error("fetch_orderbook %s 异常: %s", pair, e)

    # ──────────────────── 报告生成 ────────────────────

    def generate_report(self) -> str:
        """
        生成标准化文本报告, 喂给 AI 决策.
        数据顺序: OLDEST → NEWEST (按 prompt 要求)
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"# 市场数据报告 — {now_str}", ""]

        for pair in self.pairs:
            lines.append(f"## {pair}")
            lines.append("")

            # ── Ticker ──
            tk = self._ticker.get(pair, {})
            if tk:
                chg_pct = ((tk["last"] - tk["open24h"]) / tk["open24h"] * 100) if tk.get("open24h") else 0
                lines.append(f"### 实时行情")
                lines.append(f"- 最新价: {tk['last']}")
                lines.append(f"- 24h 高/低: {tk['high24h']} / {tk['low24h']}")
                lines.append(f"- 24h 涨跌: {chg_pct:+.2f}%")
                lines.append(f"- 24h 成交量: {tk['vol24h']:.0f} 张")
                lines.append(f"- 买一/卖一: {tk['bid']} ({tk['bid_sz']}) / {tk['ask']} ({tk['ask_sz']})")
                lines.append("")

            # ── 盘口 ──
            ob = self._orderbook.get(pair, {})
            if ob:
                lines.append(f"### 盘口深度 (5档)")
                lines.append(f"- 买盘总量: {ob['total_bid_sz']:.2f}")
                lines.append(f"- 卖盘总量: {ob['total_ask_sz']:.2f}")
                lines.append(f"- 买卖比: {ob['bid_ask_ratio']}")
                lines.append("")

            # ── 资金费率 ──
            fr = self._funding.get(pair, {})
            if fr:
                trend = fr.get("trend", "flat")
                trend_label = {"rising": "连续上升", "falling": "连续下降", "flat": "持平"}
                lines.append(f"### 资金费率")
                lines.append(f"- 当前: {fr.get('current_rate', 0):.6f}")
                lines.append(f"- 预测下期: {fr.get('next_rate', 0):.6f}")
                lines.append(f"- 近30期均值: {fr.get('avg_rate', 0):.6f}")
                lines.append(f"- 趋势: {trend_label.get(trend, trend)} ({trend})")
                lines.append("")

            # ── 多空持仓比 ──
            ls = self._long_short_ratio.get(pair, {})
            if ls and ls.get("ratio"):
                r = ls["ratio"]
                bias = "多头偏多" if r > 1.1 else "空头偏多" if r < 0.9 else "均衡"
                lines.append(f"### 多空持仓比")
                lines.append(f"- {ls.get('period', '1H')}: {r:.2f} ({bias})")
                lines.append("")

            # ── 持仓量 ──
            oi = self._oi.get(pair, 0)
            if oi:
                lines.append(f"### 持仓量 (OI)")
                lines.append(f"- 当前: {oi:.0f} 张")
                lines.append("")

            # ── 各时间框架指标（紧凑格式）──
            for tf in ["1D", "4H", "1H", "15m"]:  # 大→小
                df = self._candles.get(pair, {}).get(tf)
                if df is None or df.empty:
                    continue

                last = df.iloc[-1]
                lines.append(f"### {tf}")
                lines.append(f"O={last['open']:.1f} H={last['high']:.1f} L={last['low']:.1f} C={last['close']:.1f} V={last['vol']:.0f}")

                # 均线 (EMA + SMA 合并一行)
                ma_parts = []
                for p in EMA_PERIODS:
                    key = f"ema{p}"
                    if key in last and pd.notna(last[key]):
                        ma_parts.append(f"E{p}={last[key]:.1f}")
                for p in [50, 200]:
                    key = f"sma{p}"
                    if key in last and pd.notna(last[key]):
                        ma_parts.append(f"S{p}={last[key]:.1f}")
                if ma_parts:
                    lines.append(f"MA: {' '.join(ma_parts)}")

                # MACD 一行
                macd_line = last.get("MACD_12_26_9")
                macd_hist = last.get("MACDh_12_26_9")
                macd_sig = last.get("MACDs_12_26_9")
                if all(v is not None and pd.notna(v) for v in [macd_line, macd_hist, macd_sig]):
                    lines.append(f"MACD={macd_line:.1f} Hist={macd_hist:.1f} Sig={macd_sig:.1f}")

                # RSI + MFI + Stoch 合并一行
                momentum = []
                if "rsi14" in last and pd.notna(last["rsi14"]):
                    momentum.append(f"RSI={last['rsi14']:.0f}")
                if "mfi14" in last and pd.notna(last["mfi14"]):
                    momentum.append(f"MFI={last['mfi14']:.0f}")
                stk = [c for c in df.columns if c.startswith("STOCHk")]
                std = [c for c in df.columns if c.startswith("STOCHd")]
                if stk and pd.notna(last.get(stk[0])):
                    momentum.append(f"StochK={last[stk[0]]:.0f}")
                if std and pd.notna(last.get(std[0])):
                    momentum.append(f"StochD={last[std[0]]:.0f}")
                if momentum:
                    lines.append(f"动量: {' '.join(momentum)}")

                # ATR + ADX + 量比 合并一行
                vol_trend = []
                if "atr14" in last and pd.notna(last["atr14"]) and last["close"]:
                    atr_pct = last["atr14"] / last["close"] * 100
                    vol_trend.append(f"ATR={last['atr14']:.1f}({atr_pct:.1f}%)")
                adx_col = [c for c in df.columns if c == "ADX_14" or (c.startswith("ADX") and "R" not in c)]
                if adx_col and pd.notna(last.get(adx_col[0])):
                    vol_trend.append(f"ADX={last[adx_col[0]]:.0f}")
                if "vol_ratio" in last and pd.notna(last["vol_ratio"]):
                    vol_trend.append(f"量比={last['vol_ratio']:.2f}")
                if vol_trend:
                    lines.append(f"波动: {' '.join(vol_trend)}")

                # 布林带 → 上下轨 + 位置
                bbp = last.get("BBP_20_2.0")
                bbl = last.get("BBL_20_2.0")
                bbu = last.get("BBU_20_2.0")
                if all(v is not None and pd.notna(v) for v in [bbp, bbl, bbu]):
                    lines.append(f"BB: {bbl:.1f}~{bbu:.1f} 位置={bbp:.0%}")

                # OBV + SuperTrend + CMF + ROC 合并
                extras = []
                if "obv" in last and pd.notna(last["obv"]):
                    extras.append(f"OBV={last['obv']:.0f}")
                st_d = [c for c in df.columns if c.startswith("SUPERTd")]
                if st_d and pd.notna(last.get(st_d[0])):
                    direction = "▲多" if last[st_d[0]] > 0 else "▼空"
                    st_val = [c for c in df.columns if c.startswith("SUPERT_")]
                    val = f"={last[st_val[0]]:.1f}" if st_val and pd.notna(last.get(st_val[0])) else ""
                    extras.append(f"ST:{direction}{val}")
                if extras:
                    lines.append(f"{' | '.join(extras)}")

                # VWAP + CMF + ROC + Pivot
                extra2 = []
                if "vwap" in last and pd.notna(last["vwap"]):
                    extra2.append(f"VWAP={last['vwap']:.1f}")
                if "cmf20" in last and pd.notna(last["cmf20"]):
                    extra2.append(f"CMF={last['cmf20']:.3f}")
                if "roc12" in last and pd.notna(last["roc12"]):
                    extra2.append(f"ROC={last['roc12']:.1f}%")
                if extra2:
                    lines.append(f"{' | '.join(extra2)}")
                if "pivot" in last and pd.notna(last["pivot"]):
                    lines.append(f"Pivot: S1={last['pivot_s1']:.1f} P={last['pivot']:.1f} R1={last['pivot_r1']:.1f}")

                # 近10根K线 (收盘+高低)
                recent = df.tail(10)
                closes = [round(x, 1) for x in recent["close"].tolist()]
                highs = [round(x, 1) for x in recent["high"].tolist()]
                lows = [round(x, 1) for x in recent["low"].tolist()]
                lines.append(f"近10C: {closes}")
                lines.append(f"近10H: {highs} L: {lows}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    # ──────────────────── 状态 ────────────────────

    @property
    def is_ready(self) -> bool:
        for pair in self.pairs:
            for tf in self.timeframes:
                df = self._candles.get(pair, {}).get(tf)
                if df is None or df.empty:
                    return False
        return True


# ──────────────────── 独立运行测试 ────────────────────

async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    engine = DataEngine()
    print("正在拉取数据...")
    await engine.update()

    if engine.is_ready:
        report = engine.generate_report()
        print(report)

        # 保存报告到文件
        with open("latest_report.txt", "w") as f:
            f.write(report)
        print("\n报告已保存到 latest_report.txt")
    else:
        print("数据未就绪, 请检查网络连接")


if __name__ == "__main__":
    asyncio.run(main())
