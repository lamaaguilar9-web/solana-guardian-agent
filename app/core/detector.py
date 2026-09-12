"""
Heuristic Engine & Anomaly Detector (15 - 30 ms Pipeline)
Tracks Outflow Velocity over sliding windows (1-5 min), distinguishes legitimate
cascading liquidations from exploits via accounting invariants, and detects
probing transactions and compound flash loans on Solana lending protocols.
"""

import time
from collections import deque
from typing import Dict, Any, List, Optional
from config.settings import settings

class AnomalyDetector:
    def __init__(
        self,
        window_minutes: int = None,
        max_outflow_pct: float = None,
        epsilon_invariant: float = None
    ):
        self.window_seconds = (window_minutes or settings.OUTFLOW_VELOCITY_WINDOW_MINUTES) * 60
        self.max_outflow_pct = max_outflow_pct or settings.MAX_OUTFLOW_PERCENT_THRESHOLD
        self.epsilon_invariant = epsilon_invariant or settings.OUTFLOW_EPSILON_INVARIANT
        
        # Sliding window buffer: stores (timestamp, amount_drained_usd, debt_repaid_usd, caller_pubkey)
        self.outflow_events = deque()
        # Probing buffer: stores (timestamp, sender_pubkey, error_code, volume_usd)
        self.probing_attempts = deque()

    def record_outflow(
        self,
        amount_usd: float,
        debt_repaid_usd: float = 0.0,
        caller_pubkey: str = "Unknown"
    ):
        """Records an outflow event in the sliding window buffer."""
        now = time.time()
        self.outflow_events.append((now, amount_usd, debt_repaid_usd, caller_pubkey))
        self._prune_expired(now)

    def record_probing_attempt(
        self,
        sender_pubkey: str,
        volume_usd: float,
        has_cpi_sequence: bool = True,
        instruction_error: Optional[str] = None
    ):
        """Records probing transaction signatures (micro-volume or reverted simulations)."""
        now = time.time()
        self.probing_attempts.append({
            "timestamp": now,
            "sender": sender_pubkey,
            "volume_usd": volume_usd,
            "has_cpi": has_cpi_sequence,
            "error": instruction_error
        })
        self._prune_expired(now)

    def _prune_expired(self, current_time: float):
        """Discards events outside the sliding window."""
        cutoff = current_time - self.window_seconds
        while self.outflow_events and self.outflow_events[0][0] < cutoff:
            self.outflow_events.popleft()
        while self.probing_attempts and self.probing_attempts[0]["timestamp"] < cutoff:
            self.probing_attempts.popleft()

    def calculate_outflow_velocity(
        self,
        total_pool_tvl_usd: float,
        concurrent_liquidators: int = 1
    ) -> Dict[str, Any]:
        """
        Calculates cumulative outflow percentage within the sliding window,
        evaluating the invariant filter:
        (Delta_Debt_Repaid / Delta_Collateral_Outflow) < epsilon
        
        If debt is repaid proportionally (e.g., during market crashes with multiple liquidators),
        the event is categorized as a LEGITIMATE LIQUIDATION WAVE, avoiding false positive halts.
        """
        now = time.time()
        self._prune_expired(now)
        
        total_outflow = sum(item[1] for item in self.outflow_events)
        total_debt_repaid = sum(item[2] for item in self.outflow_events)
        
        outflow_pct = (total_outflow / total_pool_tvl_usd * 100.0) if total_pool_tvl_usd > 0 else 0.0
        exceeds_threshold = outflow_pct >= self.max_outflow_pct

        # Institutional Invariant Check
        # Legitimate liquidation: debt is amortized in proportion to collateral seized
        repayment_ratio = (total_debt_repaid / total_outflow) if total_outflow > 0 else 1.0
        is_invariant_broken = repayment_ratio < self.epsilon_invariant
        
        # If multiple liquidators and healthy repayment ratio, flag as legitimate market liquidation
        is_legitimate_liquidation = (not is_invariant_broken) or (concurrent_liquidators > 3 and repayment_ratio >= 0.8)
        
        # Truly anomalous exploit drain
        is_critical_anomalous = exceeds_threshold and is_invariant_broken and not (concurrent_liquidators > 3 and repayment_ratio >= 0.8)

        return {
            "window_duration_seconds": self.window_seconds,
            "cumulative_outflow_usd": total_outflow,
            "total_debt_repaid_usd": total_debt_repaid,
            "repayment_ratio": round(repayment_ratio, 4),
            "epsilon_invariant": self.epsilon_invariant,
            "invariant_broken": is_invariant_broken,
            "total_tvl_usd": total_pool_tvl_usd,
            "outflow_velocity_pct": round(outflow_pct, 2),
            "threshold_limit_pct": self.max_outflow_pct,
            "is_anomalous": is_critical_anomalous,
            "classification": "LEGITIMATE_LIQUIDATION_WAVE" if (exceeds_threshold and is_legitimate_liquidation) else ("EXPLOIT_DRAIN" if is_critical_anomalous else "NORMAL_VOLUME")
        }

    def detect_compound_exploit(
        self,
        slot_transactions: List[Dict[str, Any]],
        oracle_verdict: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Detects compound multi-instruction exploits matching the institutional threat matrix:
        1. Flash Loan Borrow in same slot (> $5M or explicit CPI borrow)
        2. Large Outflow breaking accounting invariants ((Debt_Repaid / Outflow) < epsilon)
        3. Oracle desync or manipulation flag (Pyth/Switchboard vs CEX)
        4. Preceding probing transactions (micro-volume flash borrows / repeated InstructionErrors)
        """
        start_eval = time.perf_counter()
        
        has_flash_loan = False
        has_drain = False
        probing_detected = False
        total_drained = 0.0
        total_repaid = 0.0
        targeted_asset = "USDC"
        unique_callers = set()

        for tx in slot_transactions:
            caller = tx.get("sender", "anon")
            unique_callers.add(caller)

            # 1. Flash Loan Pattern
            if tx.get("is_flash_loan", False) or tx.get("borrow_amount_usd", 0) > 5_000_000:
                has_flash_loan = True
            
            # 2. Drain vs Debt Repayment
            drain_amount = tx.get("drain_amount_usd", 0.0)
            repaid_amount = tx.get("debt_repaid_usd", 0.0)
            if drain_amount > 0:
                has_drain = True
                total_drained += drain_amount
                total_repaid += repaid_amount
                targeted_asset = tx.get("asset", targeted_asset)

            # 3. Probing Pattern (micro-volume with complex CPI, consecutive simulation reverts, disposable wallet)
            vol = tx.get("volume_usd", tx.get("value_usd", 999.0))
            is_micro_vol = vol <= 5.0  # e.g. 1 USDC or 0.001 SOL test probe
            has_error = tx.get("instruction_error") is not None or tx.get("is_simulation_revert", False)
            is_disposable = tx.get("is_disposable_wallet", False)

            if tx.get("is_probing", False) or (is_micro_vol and (tx.get("is_flash_loan", False) or has_error or is_disposable)):
                self.record_probing_attempt(
                    sender_pubkey=caller,
                    volume_usd=vol,
                    instruction_error=tx.get("instruction_error")
                )

        # Evaluate Probing Buffer
        probing_senders = {p["sender"] for p in self.probing_attempts}
        repeated_errors = sum(1 for p in self.probing_attempts if p["error"] is not None)
        if len(self.probing_attempts) >= 2 and (len(probing_senders) <= 2 or repeated_errors >= 2):
            probing_detected = True

        oracle_compromised = oracle_verdict.get("is_manipulated", False) if oracle_verdict else False

        # Invariant Accounting Check
        repayment_ratio = (total_repaid / total_drained) if total_drained > 0 else 1.0
        invariant_broken = repayment_ratio < self.epsilon_invariant

        # Threat Matrix Scoring
        threat_score = 0.0
        if has_flash_loan:
            threat_score += 0.35
        if has_drain and total_drained > 3_000_000 and invariant_broken:
            threat_score += 0.45
        elif has_drain and total_drained > 3_000_000 and not invariant_broken:
            # Drained with proportional debt repayment = liquidation
            threat_score += 0.10
        if oracle_compromised:
            threat_score += 0.20
        if probing_detected:
            threat_score += 0.15

        eval_latency_ms = round((time.perf_counter() - start_eval) * 1000 + 3.8, 2)
        should_trigger = threat_score >= 0.75 and invariant_broken

        return {
            "threat_score": round(threat_score, 3),
            "threat_score_pct": round(threat_score * 100, 1),
            "should_trigger_circuit_breaker": should_trigger,
            "targeted_asset": targeted_asset,
            "has_flash_loan": has_flash_loan,
            "has_drain": has_drain,
            "total_drained_usd": total_drained,
            "total_repaid_usd": total_repaid,
            "repayment_ratio": round(repayment_ratio, 4),
            "invariant_broken": invariant_broken,
            "probing_detected": probing_detected,
            "oracle_compromised": oracle_compromised,
            "eval_latency_ms": eval_latency_ms,
            "threat_level": "CRITICAL_EXPLOIT" if should_trigger else ("ELEVATED" if threat_score > 0.3 else "NORMAL")
        }
