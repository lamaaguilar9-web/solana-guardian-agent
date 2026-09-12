from app.core.protocol_adapters import (
    AnchorInstructionResolver,
    ProtocolRegistry,
    Pubkey
)

def test_anchor_discriminator_exact_resolution():
    # 1. Kamino Klend: Sha256("global:pause_reserve")[:8]
    resolver_kamino = AnchorInstructionResolver(protocol_name="kamino_klend")
    kamino_disc = ProtocolRegistry.derive_anchor_discriminator("pause_reserve")
    assert resolver_kamino.validate_discriminator(kamino_disc) is True
    assert len(resolver_kamino.discriminator) == 8

    # 2. Marginfi: Sha256("global:marginfi_group_set_bank_emergency_paused")[:8]
    resolver_mfi = AnchorInstructionResolver(protocol_name="marginfi")
    mfi_disc = ProtocolRegistry.derive_anchor_discriminator("marginfi_group_set_bank_emergency_paused")
    assert resolver_mfi.validate_discriminator(mfi_disc) is True
    assert len(resolver_mfi.discriminator) == 8

    # 3. Solend/Save: Sha256("global:pause_asset")[:8]
    resolver_solend = AnchorInstructionResolver(protocol_name="solend_save")
    solend_disc = ProtocolRegistry.derive_anchor_discriminator("pause_asset")
    assert resolver_solend.validate_discriminator(solend_disc) is True
    assert len(resolver_solend.discriminator) == 8

def test_direct_signer_vs_delegated_pda_cpi():
    prog_id = Pubkey("Kamino111111111111111111111111111111111111")
    guardian = Pubkey("GuardianWallet1111111111111111111111111111")
    market = Pubkey("7u3HeHxYDLhnCoErrtycNokbQYbWGzLs6JSDqGAv5PfF")
    reserve = Pubkey("ReserveUSDC1111111111111111111111111111111")

    # Mode A: Direct Guardian Signer (3 accounts strictly ordered)
    resolver_direct = AnchorInstructionResolver(
        protocol_name="kamino_klend",
        authorization_mode="direct_guardian_signer"
    )
    ix_direct = resolver_direct.build_instruction(prog_id, guardian, market, reserve)
    assert ix_direct["authorization_mode"] == "direct_guardian_signer"
    assert ix_direct["account_count"] == 3
    accounts = ix_direct["instruction"].accounts
    assert accounts[0].is_signer is True and accounts[0].is_writable is False  # guardian
    assert accounts[1].is_signer is False and accounts[1].is_writable is False # market
    assert accounts[2].is_signer is False and accounts[2].is_writable is True  # reserve mut

    # Mode B: Delegated PDA CPI (7 accounts including PDA, Gateway State, System Program)
    resolver_pda = AnchorInstructionResolver(
        protocol_name="kamino_klend",
        authorization_mode="delegated_pda_cpi"
    )
    ix_pda = resolver_pda.build_instruction(prog_id, guardian, market, reserve)
    assert ix_pda["authorization_mode"] == "delegated_pda_cpi"
    assert ix_pda["account_count"] == 7
    assert "Delegated PDA CPI" in ix_pda["notes"]

def test_zero_copy_reserve_header_fastpath():
    resolver = AnchorInstructionResolver(protocol_name="kamino_klend")
    
    # Construct synthetic 41-byte zero-copy header
    disc = resolver.discriminator  # 8 bytes
    market_32 = b"\xaa" * 32       # 32 bytes
    status_paused = bytes([1])     # 1 byte (1 = Paused)
    raw_data = disc + market_32 + status_paused

    header = resolver.parse_zero_copy_reserve_header(raw_data)
    assert header["valid"] is True
    assert header["is_paused"] is True
    assert header["read_mode"] == "zero_copy_bytemuck_fastpath"
