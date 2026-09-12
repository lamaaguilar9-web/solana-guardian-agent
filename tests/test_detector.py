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
