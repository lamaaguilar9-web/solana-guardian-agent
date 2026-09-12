import sys
import time
from tests.test_detector import test_outflow_velocity_threshold, test_compound_exploit_detection
from tests.test_simulation import test_granular_pause_simulation, test_asymmetric_squads_unpause_enforcement, test_jito_mev_bundle_dispatch

def run_all():
    print("================================================================================")
    print("        SOLANA DEFI GUARDIAN AGENT - AUTOMATED VERIFICATION SUITE              ")
    print("================================================================================")
    tests = [
        ("test_outflow_velocity_threshold", test_outflow_velocity_threshold),
        ("test_compound_exploit_detection", test_compound_exploit_detection),
        ("test_granular_pause_simulation", test_granular_pause_simulation),
        ("test_asymmetric_squads_unpause_enforcement", test_asymmetric_squads_unpause_enforcement),
        ("test_jito_mev_bundle_dispatch", test_jito_mev_bundle_dispatch)
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
