from fastapi import APIRouter
import time
import httpx
from config.settings import settings

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Heartbeat and live self-diagnostic monitor required by institutional specifications.
    Performs real RPC getSlot query and Pyth Hermes endpoint check.
    """
    rpc_online = False
    rpc_slot = None
    pyth_online = False
    pyth_price = None

    async with httpx.AsyncClient() as client:
        # 1. Live Solana RPC check
        try:
            rpc_resp = await client.post(
                settings.SOLANA_RPC_URL,
                json={"jsonrpc": "2.0", "id": 1, "method": "getSlot"},
                timeout=2.5
            )
            if rpc_resp.status_code == 200:
                data = rpc_resp.json()
                if "result" in data:
                    rpc_slot = data["result"]
                    rpc_online = True
        except Exception:
            rpc_online = False

        # 2. Live Pyth Hermes oracle check (SOL/USD feed)
        try:
            pyth_resp = await client.get(
                "https://hermes.pyth.network/v2/updates/price/latest?ids[]=ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",
                timeout=2.5
            )
            if pyth_resp.status_code == 200:
                data = pyth_resp.json()
                if "parsed" in data and len(data["parsed"]) > 0:
                    parsed = data["parsed"][0]["price"]
                    pyth_price = float(parsed["price"]) * (10 ** int(parsed["expo"]))
                    pyth_online = True
        except Exception:
            pyth_online = False

    is_healthy = rpc_online or pyth_online

    return {
        "status": "HEALTHY" if is_healthy else "DEGRADED",
        "agent": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "heartbeat_timestamp": time.time(),
        "performance_profile": {
            "target_latency_cap": "< 30 ms (Target: 26 ms)",
            "pipeline_stage_targets": {
                "stage_1_ingestion_target": "< 8 ms (RPC Poll / Geyser stream)",
                "stage_2_evaluation_target": "< 6 ms (Anomaly heuristic & Oracle cross-check)",
                "stage_3_execution_target": "< 12 ms (KMS signing & Jito bundle submission)"
            }
        },
        "integrations": {
            "solana_rpc_online": rpc_online,
            "solana_current_slot": rpc_slot,
            "pyth_oracle_online": pyth_online,
            "pyth_sol_price": pyth_price,
            "jito_block_engine_live": False if settings.JITO_DRY_RUN else True,
            "jito_execution_mode": "JITO_DRY_RUN" if settings.JITO_DRY_RUN else "JITO_LIVE_BUNDLE",
            "kms_signer_mode": settings.KMS_PROVIDER,
            "squads_recovery_gate": "SIMULATED_RECOVERY_GATE"
        }
    }
