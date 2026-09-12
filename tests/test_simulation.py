from app.core.simulator import StateSimulator
from app.security.kms_signer import KMSSecuritySigner
from app.core.jito_executor import JitoMEVExecutor

def test_granular_pause_simulation():
    simulator = StateSimulator()
    pool_state = {"available_liquidity_usd": 30_000_000.0}
    verdict = {"total_drained_usd": 6_000_000.0, "targeted_asset": "USDC"}

    sim = simulator.simulate_emergency_pause(pool_state, verdict)
    assert sim["simulation_valid"] is True
    assert sim["asset_targeted"] == "USDC"
    assert sim["liquidity_preserved_usd"] > 0
    assert "pause_asset(token='USDC')" in sim["simulated_instruction"]

def test_asymmetric_squads_unpause_enforcement():
    signer = KMSSecuritySigner()
    
    # 1. Sign pause (permitted under RBAC)
    pause_sig = signer.sign_emergency_pause("USDC", 446058200)
    assert pause_sig["authorized"] is True
    assert pause_sig["instruction"] == "guardian_pause"

    # 2. Attempt unauthorized unilateral unpause (blocked)
    unauth_attempt = signer.verify_squads_multisig_recovery("short_sig", threshold_signatures=1)
    assert unauth_attempt["unfreeze_permitted"] is False

    # 3. Legitimate Squads 3/5 multisig unpause (permitted)
    valid_squads_sig = "5" * 64
    valid_attempt = signer.verify_squads_multisig_recovery(valid_squads_sig, threshold_signatures=3)
    assert valid_attempt["unfreeze_permitted"] is True
    assert valid_attempt["recovery_authority"] == "Squads_Multisig_Verified"

def test_jito_mev_bundle_dispatch():
    executor = JitoMEVExecutor()
    fake_kms = {"signature_hex": "0xabcdef123456"}
    
    # 1. Normal VaR-scaled dynamic tip:
    # VaR = $2,000,000, SOL = $140 -> VaR in SOL = 14,285 SOL = 1.428e13 lamports
    # VaR * 0.005 is high, capped at MAX_PRIORITY_FEE (2 SOL = 2,000,000,000 lamports)
    bundle = executor.dispatch_emergency_bundle("USDC", fake_kms, slot=446058300, value_at_risk_usd=2_000_000.0)
    assert bundle["execution_status"] == "COMMITTED_IN_NEXT_SLOT"
    assert bundle["channel"] == "gRPC_Direct_Block_Engine_Stream"
    assert len(bundle["regional_endpoints_broadcasted"]) >= 4
    assert bundle["protocol_wide_halt"] is False
    assert bundle["isolated_asset"] == "USDC"
    assert ("pause_reserve" in bundle["action_executed"] or "pause_asset" in bundle["action_executed"])
    assert bundle["target_protocol"] in ["kamino_klend", "generic_anchor", "marginfi", "solend_save"]
    assert len(bundle["discriminator_hex"]) == 16  # 8 bytes hex
    assert "Instruction" in bundle["anchor_instruction"]
    assert bundle["dispatch_latency_ms"] < 25.0

    # 2. Severe drain triggers EMERGENCY_FIXED tip
    severe_bundle = executor.dispatch_emergency_bundle(
        "USDC", fake_kms, slot=446058301, value_at_risk_usd=10_000_000.0, is_severe_drain=True
    )
    assert severe_bundle["tip_strategy"] == "EMERGENCY_FIXED"
    assert severe_bundle["priority_tip_lamports"] == 1_000_000_000  # 1.0 SOL fixed emergency tip
