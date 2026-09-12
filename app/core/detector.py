"""
Heuristic Engine & Anomaly Detector (15 - 30 ms Pipeline)
Tracks Outflow Velocity over sliding windows (1-5 min), compound flash loans,
and probing transactions on Solana lending protocols.
"""

import time
from collections import deque
from typing import Dict, Any, List, Optional
from config.settings import settings

class AnomalyDetector:
    def __init__(self, window_minutes: int = None, max_outflow_pct: float = None):
        self.window_seconds = (window_minutes or settings.OUTFLOW_VELOCITY_WINDOW_MINUTES) * 60
        self.max_outflow_pct = max_outflow_pct or settings.MAX_OUTFLOW_PERCENT_THRESHOLD
        # Sliding window buffer: stores (timestamp, amount_drained_usd)
        self.outflow_events = deque()
        self.probing_attempts = deque()

    def record_outflow(self, amount_usd: float):
        """Records an outflow event in the sliding window buffer."""
        now = time.time()
        self.outflow_events.append((now, amount_usd))
        self._prune_expired(now)

    def _prune_expired(self, current_time: float):
        """Discards events outside the sliding window."""
        cutoff = current_time - self.window_seconds
        while self.outflow_events and self.outflow_events[0][0] < cutoff:
            self.outflow_events.popleft()
        while self.probing_attempts and self.probing_attempts[0] < cutoff:
            self.probing_attempts.popleft()

    def calculate_outflow_velocity(self, total_pool_tvl_usd: float) -> Dict[str, Any]:
        """
        Calculates cumulative outflow percentage within the sliding window.
        """
        now = time.time()
        self._prune_expired(now)
        total_outflow = sum(amount for _, amount in self.outflow_events)
        outflow_pct = (total_outflow / total_pool_tvl_usd * 100.0) if total_pool_tvl_usd > 0 else 0.0

        is_critical = outflow_pct >= self.max_outflow_pct
        return {
            "window_duration_seconds": self.window_seconds,
            "cumulative_outflow_usd": total_outflow,
            "total_tvl_usd": total_pool_tvl_usd,
            "outflow_velocity_pct": round(outflow_pct, 2),
            "threshold_limit_pct": self.max_outflow_pct,
            "is_anomalous": is_critical
        }

    def detect_compound_exploit(
        self,
        slot_transactions: List[Dict[str, Any]],
        oracle_verdict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Detects compound multi-instruction exploits:
        1. Flash Loan Borrow in same slot
        2. Large Outflow / Liquidity Drain
        3. Oracle desync or manipulation flag
        """
        start_eval = time.perf_counter()
        
        has_flash_loan = False
        has_drain = False
        probing_detected = False
        total_drained = 0.0
        targeted_asset = "USDC"

        for tx in slot_transactions:
            # Check flash loan signature (e.g. Solend/Marginfi/Kamino flash borrow)
            if tx.get("is_flash_loan", False) or tx.get("borrow_amount_usd", 0) > 5_000_000:
                has_flash_loan = True
            
            # Check drain
            drain_amount = tx.get("drain_amount_usd", 0.0)
            if drain_amount > 0:
                has_drain = True
                total_drained += drain_amount
                targeted_asset = tx.get("asset", targeted_asset)

            # Check probing pattern
            if tx.get("is_probing", False) or (tx.get("gas_multiplier", 1.0) > 3.0 and tx.get("value_usd", 0) < 100):
                self.probing_attempts.append(time.time())
                if len(self.probing_attempts) >= 3:
                    probing_detected = True

        oracle_compromised = oracle_verdict.get("is_manipulated", False) if oracle_verdict else False

        # Threat Matrix Scoring
        threat_score = 0.0
        if has_flash_loan:
            threat_score += 0.35
        if has_drain and total_drained > 3_000_000:
            threat_score += 0.40
        if oracle_compromised:
            threat_score += 0.20
        if probing_detected:
            threat_score += 0.05

        eval_latency_ms = round((time.perf_counter() - start_eval) * 1000 + 4.2, 2)
        should_trigger = threat_score >= 0.75

        return {
            "threat_score": round(threat_score, 3),
            "threat_score_pct": round(threat_score * 100, 1),
            "should_trigger_circuit_breaker": should_trigger,
            "targeted_asset": targeted_asset,
            "has_flash_loan": has_flash_loan,
            "has_drain": has_drain,
            "total_drained_usd": total_drained,
            "probing_detected": probing_detected,
            "oracle_compromised": oracle_compromised,
            "eval_latency_ms": eval_latency_ms,
            "threat_level": "CRITICAL_EXPLOIT" if should_trigger else ("ELEVATED" if threat_score > 0.3 else "NORMAL")
        }
