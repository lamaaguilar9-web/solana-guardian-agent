"""
Multi-Oracle Cross-Validation Service (Pyth Hermes vs Binance CEX Spot)
Parche de Desconexión de Switchboard (Cierre 25-Sept-2026).
Compara únicamente Pyth Hermes (Pull Oracle) contra Binance CEX Reference.
Si Switchboard está deshabilitado, no emite requests ni altera el cálculo de desvío.
Protocol: Sentinel Fleet Technologies (sentinelfleet.tech)
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Any
import aiohttp

from config.settings import settings

logger = logging.getLogger("sentinel.oracle")


class OracleService:
    def __init__(
        self,
        pyth_hermes_url: str = "https://hermes.pyth.network",
        binance_api_url: str = "https://api.binance.com",
        max_divergence_pct: float = None,
        staleness_limit: int = None
    ):
        self.pyth_hermes_url = pyth_hermes_url
        self.binance_api_url = binance_api_url
        self.switchboard_enabled = False  # Desactivado formalmente por cese de servicio 25-Sept-2026
        self.max_divergence_pct = max_divergence_pct or getattr(settings, "ORACLE_MAX_DIVERGENCE_PCT", 1.5)
        self.staleness_limit = staleness_limit or getattr(settings, "ORACLE_STALENESS_SECONDS", 120)
        self.cache: Dict[str, Dict[str, Any]] = {}

    async def get_pyth_price(self, price_feed_id: str, session: aiohttp.ClientSession) -> Optional[float]:
        try:
            url = f"{self.pyth_hermes_url}/v2/updates/price/latest?ids[]={price_feed_id}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    parsed = data["parsed"][0]["price"]
                    price = float(parsed["price"]) * (10 ** int(parsed["expo"]))
                    return price
        except Exception as e:
            logger.error(f"Error consultando Pyth Hermes ({price_feed_id}): {e}")
        return None

    async def get_cex_reference_price(self, symbol: str, session: aiohttp.ClientSession) -> Optional[float]:
        try:
            url = f"{self.binance_api_url}/api/v3/ticker/price?symbol={symbol}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=1.5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data["price"])
        except Exception as e:
            logger.error(f"Error consultando CEX Reference ({symbol}): {e}")
        return None

    async def evaluate_divergence(self, token_symbol: str, pyth_id: str, cex_pair: str) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            pyth_price, cex_price = await asyncio.gather(
                self.get_pyth_price(pyth_id, session),
                self.get_cex_reference_price(cex_pair, session)
            )

        if not pyth_price or not cex_price:
            return {
                "token": token_symbol,
                "status": "INSUFFICIENT_DATA",
                "divergence_pct": 0.0,
                "is_anomaly": False,
                "is_manipulated": False,
                "switchboard_status": "DEPRECATED_OFFLINE"
            }

        divergence = abs(pyth_price - cex_price) / cex_price
        is_anomaly = (divergence * 100.0) > self.max_divergence_pct  # Umbral de divergencia anómala > 1.5%

        result = {
            "token": token_symbol,
            "pyth_price": pyth_price,
            "cex_price": cex_price,
            "switchboard_status": "DEPRECATED_OFFLINE",
            "divergence_pct": round(divergence * 100, 3),
            "is_anomaly": is_anomaly,
            "is_manipulated": is_anomaly,
            "status": "ANOMALY_DETECTED" if is_anomaly else "NORMAL"
        }
        self.cache[token_symbol] = result
        return result

    def validate_price_feed(
        self,
        token: str,
        pyth_price: float,
        switchboard_price: float,
        cex_spot_ref: float,
        pyth_timestamp: float = None
    ) -> Dict[str, Any]:
        """
        Validates Pyth against off-chain spot reference (Binance CEX).
        Switchboard is safely bypassed and marked as DEPRECATED_OFFLINE.
        """
        now = time.time()
        pyth_ts = pyth_timestamp or now
        age_seconds = now - pyth_ts

        # 1. Staleness check
        is_stale = age_seconds > self.staleness_limit

        # 2. Divergence calculation strictly Pyth vs CEX Reference (Switchboard ignored)
        ref_price = cex_spot_ref if cex_spot_ref > 0 else pyth_price
        pyth_dev_pct = abs(pyth_price - ref_price) / ref_price * 100.0
        max_detected_dev = pyth_dev_pct

        # 3. Threat Assessment
        is_manipulated = max_detected_dev >= self.max_divergence_pct or is_stale

        return {
            "token": token,
            "pyth_price": pyth_price,
            "switchboard_price": None if not self.switchboard_enabled else switchboard_price,
            "switchboard_status": "DEPRECATED_OFFLINE",
            "cex_reference_price": cex_spot_ref,
            "max_divergence_pct": round(max_detected_dev, 3),
            "is_stale": is_stale,
            "feed_age_seconds": round(age_seconds, 2),
            "is_manipulated": is_manipulated,
            "is_anomaly": is_manipulated,
            "oracle_status": "CRITICAL_DIVERGENCE" if is_manipulated else "SYNCHRONIZED",
            "action_required": "DEGRADE_LIQUIDATIONS_AND_PAUSE" if is_manipulated else "NORMAL"
        }
