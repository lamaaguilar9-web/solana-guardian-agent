import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # System Info
    PROJECT_NAME: str = "Solana DeFi Guardian Agent"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "production"
    
    # 1. Ingestion (Yellowstone Geyser gRPC & Solana RPC)
    SOLANA_RPC_URL: str = Field(default="https://api.mainnet-beta.solana.com", env="SOLANA_RPC_URL")
    SOLANA_GEYSER_GRPC_URL: str = Field(default="grpc://yellowstone-mainnet.helius.xyz:443", env="SOLANA_GEYSER_GRPC_URL")
    GEYSER_AUTH_TOKEN: Optional[str] = Field(default=None, env="GEYSER_AUTH_TOKEN")
    
    # 2. Execution & Jito MEV
    JITO_BLOCK_ENGINE_URL: str = Field(default="https://mainnet.block-engine.jito.wtf/api/v1/bundles", env="JITO_BLOCK_ENGINE_URL")
    JITO_REGIONAL_ENDPOINTS: list = [
        "https://frankfurt.mainnet.block-engine.jito.wtf",
        "https://ny.mainnet.block-engine.jito.wtf",
        "https://slc.mainnet.block-engine.jito.wtf",
        "https://amsterdam.mainnet.block-engine.jito.wtf",
        "https://tokyo.mainnet.block-engine.jito.wtf"
    ]
    MAX_PRIORITY_FEE_LAMPORTS: int = Field(default=2_000_000_000, env="MAX_PRIORITY_FEE_LAMPORTS")  # 2.0 SOL Cap
    DEFAULT_JITO_TIP_LAMPORTS: int = Field(default=100_000, env="DEFAULT_JITO_TIP_LAMPORTS")
    JITO_TIP_P99_LAMPORTS: int = Field(default=5_000_000, env="JITO_TIP_P99_LAMPORTS")  # p99 floor baseline
    EMERGENCY_FIXED_TIP_LAMPORTS: int = Field(default=1_000_000_000, env="EMERGENCY_FIXED_TIP_LAMPORTS")  # 1.0 SOL emergency tip
    
    # Invariant Filters (Exploit vs Legitimate Liquidations)
    OUTFLOW_EPSILON_INVARIANT: float = Field(default=0.05, env="OUTFLOW_EPSILON_INVARIANT")  # Debt repaid / collateral threshold
    TARGET_PROTOCOL: str = Field(default="kamino_klend", env="TARGET_PROTOCOL")  # kamino_klend | marginfi | solend_save | generic_anchor
    AUTHORIZATION_MODE: str = Field(default="direct_guardian_signer", env="AUTHORIZATION_MODE")  # direct_guardian_signer | delegated_pda_cpi
    LENDING_PROGRAM_ID: str = Field(default="Kamino111111111111111111111111111111111111", env="LENDING_PROGRAM_ID")
    LENDING_MARKET_PUBKEY: str = Field(default="7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF", env="LENDING_MARKET_PUBKEY")
    GATEWAY_PROGRAM_ID: str = Field(default="Gate111111111111111111111111111111111111111", env="GATEWAY_PROGRAM_ID")
    
    # 3. Key Management & RBAC
    KMS_PROVIDER: str = Field(default="local_simulated", env="KMS_PROVIDER")
    KMS_KEY_ID: str = Field(default="projects/sentinel-lab/locations/global/keyRings/guardian/cryptoKeys/pause-signer", env="KMS_KEY_ID")
    SQUADS_MULTISIG_PROGRAM_ID: str = Field(default="SQDS4ep65T869zMMBKyuUq6aD6EgTu8psMjkvj52pCf", env="SQUADS_MULTISIG_PROGRAM_ID")
    SQUADS_VAULT_ADDRESS: str = Field(default="SquadsRecoveryVaultAddress11111111111111111", env="SQUADS_VAULT_ADDRESS")
    
    # 4. Oracles & Outflow
    PYTH_PRICE_SERVICE_URL: str = Field(default="https://hermes.pyth.network", env="PYTH_PRICE_SERVICE_URL")
    ORACLE_MAX_DIVERGENCE_PCT: float = Field(default=3.5, env="ORACLE_MAX_DIVERGENCE_PCT")
    ORACLE_STALENESS_SECONDS: int = Field(default=15, env="ORACLE_STALENESS_SECONDS")
    OUTFLOW_VELOCITY_WINDOW_MINUTES: int = Field(default=5, env="OUTFLOW_VELOCITY_WINDOW_MINUTES")
    MAX_OUTFLOW_PERCENT_THRESHOLD: float = Field(default=15.0, env="MAX_OUTFLOW_PERCENT_THRESHOLD")
    
    # 5. Incident Notification Webhooks
    ALERT_WEBHOOK_URL: Optional[str] = Field(default=None, env="ALERT_WEBHOOK_URL")
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: Optional[str] = Field(default=None, env="TELEGRAM_CHAT_ID")
    PAGERDUTY_ROUTING_KEY: Optional[str] = Field(default=None, env="PAGERDUTY_ROUTING_KEY")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
