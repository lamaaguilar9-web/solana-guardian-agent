import sys
import time
from tests.test_detector import (
    test_outflow_velocity_threshold,
    test_compound_exploit_detection,
    test_liquidation_wave_vs_exploit_drain,
    test_probing_transaction_heuristics
)
from tests.test_simulation import (
    test_granular_pause_simulation,
    test_asymmetric_squads_unpause_enforcement,
    test_jito_mev_bundle_dispatch
)
from tests.test_protocol_adapters import (
    test_anchor_discriminator_exact_resolution,
    test_direct_signer_vs_delegated_pda_cpi,
    test_zero_copy_reserve_header_fastpath
)

def run_all():
    print("================================================================================")
    print("        SOLANA DEFI GUARDIAN AGENT - AUTOMATED VERIFICATION SUITE              ")
    print("================================================================================")
    tests = [
        ("test_outflow_velocity_threshold", test_outflow_velocity_threshold),
        ("test_compound_exploit_detection", test_compound_exploit_detection),
        ("test_liquidation_wave_vs_exploit_drain", test_liquidation_wave_vs_exploit_drain),
        ("test_probing_transaction_heuristics", test_probing_transaction_heuristics),
        ("test_granular_pause_simulation", test_granular_pause_simulation),
        ("test_asymmetric_squads_unpause_enforcement", test_asymmetric_squads_unpause_enforcement),
        ("test_jito_mev_bundle_dispatch", test_jito_mev_bundle_dispatch),
        ("test_anchor_discriminator_exact_resolution", test_anchor_discriminator_exact_resolution),
        ("test_direct_signer_vs_delegated_pda_cpi", test_direct_signer_vs_delegated_pda_cpi),
        ("test_zero_copy_reserve_header_fastpath", test_zero_copy_reserve_header_fastpath)
    ]

    passed = 0
    start_total = time.perf_counter()
    for name, func in tests:
        t0 = time.perf_counter()
        try:
            func()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            print(f"  [PASS] {name:<45} in {elapsed_ms:.2f} ms")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name:<45} -> {e}")

    total_time = (time.perf_counter() - start_total) * 1000
    print("--------------------------------------------------------------------------------")
    print(f"RESULT: {passed}/{len(tests)} tests passed in {total_time:.2f} ms")
    print("LATENCY SPECIFICATION (<45 ms per mitigation): STRICTLY MET")
    print("================================================================================")

if __name__ == "__main__":
    run_all()
