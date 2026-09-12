"""
Multi-Oracle Cross-Validation Service (Pyth Network & Switchboard)
Detects oracle desynchronization, price deviation (>3.5%), and staleness.
Includes EVM Chainlink compatibility interface for cross-chain deployment.
"""

import time
import logging
from typing import Dict, Any

from config.settings import settings

logger = logging.getLogger("OracleService")

class OracleService:
    def __init__(self, max_divergence_pct: float = None, staleness_limit: int = None):
        self.max_divergence_pct = max_divergence_pct or settings.ORACLE_MAX_DIVERGENCE_PCT
        self.staleness_limit = staleness_limit or settings.ORACLE_STALENESS_SECONDS

    def validate_price_feed(
        self,
        token: str,
        pyth_price: float,
        switchboard_price: float,
        cex_spot_ref: float,
        pyth_timestamp: float = None
    ) -> Dict[str, Any]:
        """
        Validates Pyth vs Switchboard against off-chain spot reference (Binance/Coinbase).
        Detects oracle distortion before lending protocol liquidation cascades occur.
        """
        now = time.time()
        pyth_ts = pyth_timestamp or now
        age_seconds = now - pyth_ts

        # 1. Staleness check
        is_stale = age_seconds > self.staleness_limit

        # 2. Divergence calculation
        ref_price = cex_spot_ref if cex_spot_ref > 0 else pyth_price
        pyth_dev_pct = abs(pyth_price - ref_price) / ref_price * 100.0
        switchboard_dev_pct = abs(switchboard_price - ref_price) / ref_price * 100.0
        max_detected_dev = max(pyth_dev_pct, switchboard_dev_pct)

        # 3. Threat Assessment
        is_manipulated = max_detected_dev >= self.max_divergence_pct or is_stale

        return {
            "token": token,
            "pyth_price": pyth_price,
            "switchboard_price": switchboard_price,
            "cex_reference_price": cex_spot_ref,
            "max_divergence_pct": round(max_detected_dev, 3),
            "is_stale": is_stale,
            "feed_age_seconds": round(age_seconds, 2),
            "is_manipulated": is_manipulated,
            "oracle_status": "CRITICAL_DIVERGENCE" if is_manipulated else "SYNCHRONIZED",
            "action_required": "DEGRADE_LIQUIDATIONS_AND_PAUSE" if is_manipulated else "NORMAL"
        }

    # EVM Chainlink Adaptation Hook
    def validate_chainlink_aggregator_evm(self, round_id: int, price: float, updated_at: int) -> Dict[str, Any]:
        """
        EVM AggregatorV3Interface fallback hook (Ethereum / Arbitrum / Base).
        Ensures cross-chain portability.
        """
        now = time.time()
        age = now - updated_at
        is_stale = age > self.staleness_limit
        return {
            "adapter": "Chainlink_AggregatorV3",
            "round_id": round_id,
            "price": price,
            "is_stale": is_stale,
            "status": "STALE_ORACLE" if is_stale else "OK"
        }
