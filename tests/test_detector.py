from app.core.detector import AnomalyDetector
from app.services.oracle_service import OracleService

def test_outflow_velocity_threshold():
    detector = AnomalyDetector(window_minutes=5, max_outflow_pct=15.0)
    pool_tvl = 10_000_000.0

    # Normal withdrawal 5%
    detector.record_outflow(500_000.0)
    v1 = detector.calculate_outflow_velocity(pool_tvl)
    assert v1["is_anomalous"] is False
    assert v1["outflow_velocity_pct"] == 5.0

    # Sudden surge: additional 12% ($1.2M)
    detector.record_outflow(1_200_000.0)
    v2 = detector.calculate_outflow_velocity(pool_tvl)
    assert v2["is_anomalous"] is True
    assert v2["outflow_velocity_pct"] == 17.0

def test_compound_exploit_detection():
    detector = AnomalyDetector()
    oracles = OracleService()

    # Normal oracle feed
    normal_oracle = oracles.validate_price_feed("SOL", 140.0, 140.2, 140.1)
    assert normal_oracle["is_manipulated"] is False

    # Normal transaction batch
    normal_batch = [{"is_flash_loan": False, "drain_amount_usd": 1000.0}]
    eval_normal = detector.detect_compound_exploit(normal_batch, normal_oracle)
    assert eval_normal["should_trigger_circuit_breaker"] is False
    assert eval_normal["threat_level"] == "NORMAL"

    # Attack batch: Flash Loan + Large Drain + Oracle Desync (Pyth deviated 8%)
    bad_oracle = oracles.validate_price_feed("SOL", 125.0, 126.0, 140.0)
    assert bad_oracle["is_manipulated"] is True

    attack_batch = [
        {"is_flash_loan": True, "borrow_amount_usd": 15_000_000.0},
        {"drain_amount_usd": 5_500_000.0, "asset": "USDC"}
    ]
    eval_attack = detector.detect_compound_exploit(attack_batch, bad_oracle)
    assert eval_attack["should_trigger_circuit_breaker"] is True
    assert eval_attack["threat_level"] == "CRITICAL_EXPLOIT"
    assert eval_attack["targeted_asset"] == "USDC"
    assert eval_attack["invariant_broken"] is True

def test_liquidation_wave_vs_exploit_drain():
    detector = AnomalyDetector(window_minutes=5, max_outflow_pct=15.0, epsilon_invariant=0.05)
    pool_tvl = 10_000_000.0

    # Scenario A: Massive Market Crash - Legitimate Cascade Liquidations
    # $2,000,000 liquidated, but $1,900,000 debt was legitimately repaid by multiple bots
    detector.record_outflow(amount_usd=2_000_000.0, debt_repaid_usd=1_900_000.0, caller_pubkey="LiquidatorBotA")
    liq_eval = detector.calculate_outflow_velocity(pool_tvl, concurrent_liquidators=6)
    assert liq_eval["outflow_velocity_pct"] == 20.0
    assert liq_eval["repayment_ratio"] == 0.95
    assert liq_eval["invariant_broken"] is False
    assert liq_eval["is_anomalous"] is False
    assert liq_eval["classification"] == "LEGITIMATE_LIQUIDATION_WAVE"

    # Scenario B: Exploit Drain - $2,000,000 withdrawn with 0 debt repaid
    exploit_detector = AnomalyDetector(window_minutes=5, max_outflow_pct=15.0, epsilon_invariant=0.05)
    exploit_detector.record_outflow(amount_usd=2_000_000.0, debt_repaid_usd=0.0, caller_pubkey="Exploiter1111")
    exploit_eval = exploit_detector.calculate_outflow_velocity(pool_tvl, concurrent_liquidators=1)
    assert exploit_eval["outflow_velocity_pct"] == 20.0
    assert exploit_eval["repayment_ratio"] == 0.0
    assert exploit_eval["invariant_broken"] is True
    assert exploit_eval["is_anomalous"] is True
    assert exploit_eval["classification"] == "EXPLOIT_DRAIN"

def test_probing_transaction_heuristics():
    detector = AnomalyDetector()
    
    # Send 2 micro-volume probes with simulated revert
    tx_probe_1 = {
        "sender": "AttackerTestKey",
        "volume_usd": 1.0,
        "is_flash_loan": True,
        "instruction_error": "InstructionError: Custom(6001)"
    }
    tx_probe_2 = {
        "sender": "AttackerTestKey",
        "volume_usd": 0.5,
        "is_flash_loan": True,
        "instruction_error": "InstructionError: Custom(6001)"
    }
    
    eval_probe = detector.detect_compound_exploit([tx_probe_1, tx_probe_2])
    assert eval_probe["probing_detected"] is True


def test_oracle_3pct_circuit_breaker():
    """Directive SF-OPS-2026-NOV09: Oracle Divergence Circuit Breaker at exactly 3.0%."""
    oracles = OracleService()
    
    # Baseline: SOL at $100.0 CEX spot
    # Case A: 2.5% divergence -> Allowed (SYNCHRONIZED)
    normal_feed = oracles.validate_price_feed("SOL", pyth_price=102.5, switchboard_price=0.0, cex_spot_ref=100.0)
    assert normal_feed["is_manipulated"] is False
    assert normal_feed["oracle_status"] == "SYNCHRONIZED"
    assert normal_feed["action_required"] == "NORMAL"

    # Case B: 3.1% divergence -> Circuit Breaker Triggered (CRITICAL_DIVERGENCE)
    critical_feed = oracles.validate_price_feed("SOL", pyth_price=103.1, switchboard_price=0.0, cex_spot_ref=100.0)
    assert critical_feed["is_manipulated"] is True
    assert critical_feed["oracle_status"] == "CRITICAL_DIVERGENCE"
    assert critical_feed["action_required"] == "DEGRADE_LIQUIDATIONS_AND_PAUSE"


def test_volumetric_burst_anomaly_detection():
    """Directive SF-OPS-2026-NOV09: Loopscale DEX burst cross-check with Yellowstone gRPC."""
    oracles = OracleService()

    # Case A: High volume (4x surge) but low divergence (0.5%) -> No false alarm
    burst_check_normal = oracles.check_volumetric_burst(current_volume_usd=400_000.0, baseline_volume_usd=100_000.0, divergence_pct=0.5)
    assert burst_check_normal["is_burst"] is False

    # Case B: High volume surge (3.5x) AND divergence >= 2.0% -> Pre-emptive circuit triggered
    burst_check_attack = oracles.check_volumetric_burst(current_volume_usd=350_000.0, baseline_volume_usd=100_000.0, divergence_pct=2.3)
    assert burst_check_attack["is_burst"] is True
    assert burst_check_attack["status"] == "VOLUMETRIC_BURST_CIRCUIT_TRIGGERED"

    # Feed level test: DEX surge integrated into validate_price_feed
    feed_burst = oracles.validate_price_feed(
        token="SOL",
        pyth_price=102.2,
        switchboard_price=0.0,
        cex_spot_ref=100.0,
        dex_spot_price=102.2,
        dex_volume_surge_ratio=3.5
    )
    assert feed_burst["is_volumetric_burst"] is True
    assert feed_burst["is_manipulated"] is True
    assert feed_burst["action_required"] == "DEGRADE_LIQUIDATIONS_AND_PAUSE"
