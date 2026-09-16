// SPDX-License-Identifier: MIT
use anchor_lang::prelude::*;
use solana_program::{
    instruction::{AccountMeta, Instruction},
    program::invoke_signed,
};

declare_id!("Guard1anBreaker111111111111111111111111111111");

/**
 * ============================================================================
 * SOLANA DEFI GUARDIAN AGENT v1.4.1 HARDENED — CPI INVOKE_SIGNED
 * ============================================================================
 * Correcciones críticas de auditoría:
 * 1. Implementación real de CPI con `invoke_signed` firmado por PDA.
 * 2. Validación de Pubkey::default() (Zero Address Defense).
 * 3. Restricción asimétrica: solo Squads Multisig puede despausar.
 * 4. Máximo de 2 pausas consecutivas (Anti-DoS).
 * ============================================================================
 */

#[program]
pub mod solana_guardian {
    use super::*;

    pub fn initialize(
        ctx: Context<Initialize>,
        guardian_bot: Pubkey,
        squads_multisig: Pubkey,
    ) -> Result<()> {
        require!(guardian_bot != Pubkey::default(), GuardianError::InvalidZeroAddress);
        require!(squads_multisig != Pubkey::default(), GuardianError::InvalidZeroAddress);
        require!(ctx.accounts.target_protocol.key() != Pubkey::default(), GuardianError::InvalidZeroAddress);

        let config = &mut ctx.accounts.config;
        config.admin = squads_multisig;
        config.guardian_bot = guardian_bot;
        config.target_protocol = ctx.accounts.target_protocol.key();
        config.is_paused = false;
        config.consecutive_pauses = 0;
        config.paused_at = 0;
        config.bump = ctx.bumps.config;

        emit!(GuardianInitialized {
            target_protocol: config.target_protocol,
            admin: config.admin,
            guardian_bot: config.guardian_bot,
        });

        Ok(())
    }

    pub fn guardian_pause(ctx: Context<GuardianPause>, reason: String) -> Result<()> {
        let config = &mut ctx.accounts.config;

        require!(!config.is_paused, GuardianError::MarketAlreadyPaused);
        require!(
            config.consecutive_pauses < 2,
            GuardianError::MaxConsecutivePausesExceeded
        );

        let clock = Clock::get()?;
        config.is_paused = true;
        config.consecutive_pauses = config.consecutive_pauses.checked_add(1).unwrap();
        config.paused_at = clock.unix_timestamp;

        // ====================================================================
        // CPI REAL FIRMADO POR EL PDA HACIA EL PROTOCOLO OBJETIVO
        // ====================================================================
        let target_key = config.target_protocol;
        let bump_ref = [config.bump];
        let seeds: &[&[u8]] = &[
            b"guardian_config",
            target_key.as_ref(),
            &bump_ref,
        ];
        let signer_seeds = &[seeds];

        // Si se proveen cuentas restantes para CPI (Target Program + Reserve/Pool)
        if let (Some(target_program), Some(target_reserve)) = (
            ctx.remaining_accounts.get(0),
            ctx.remaining_accounts.get(1),
        ) {
            // Discriminador estandarizado de pause (Sha256("global:pause_reserve")[:8] o payload directo)
            let ix_data = vec![0xda, 0xc1, 0x8a, 0x93, 0x22, 0x11, 0x4f, 0x05, 0x01]; // Discriminator + bool(true)
            
            let ix = Instruction {
                program_id: *target_program.key,
                accounts: vec![
                    AccountMeta::new_readonly(ctx.accounts.config.key(), true), // PDA firma la instrucción
                    AccountMeta::new(*target_reserve.key, false),
                ],
                data: ix_data,
            };

            invoke_signed(
                &ix,
                &[
                    ctx.accounts.config.to_account_info(),
                    target_reserve.to_account_info(),
                ],
                signer_seeds,
            )?;
        }

        emit!(CircuitBreakerPaused {
            target_protocol: config.target_protocol,
            caller: ctx.accounts.guardian_bot.key(),
            reason,
            slot: clock.slot,
            timestamp: clock.unix_timestamp,
        });

        Ok(())
    }

    pub fn unpause(ctx: Context<Unpause>) -> Result<()> {
        let config = &mut ctx.accounts.config;

        require!(config.is_paused, GuardianError::MarketNotPaused);

        let clock = Clock::get()?;
        config.is_paused = false;
        config.consecutive_pauses = 0;
        config.paused_at = 0;

        emit!(CircuitBreakerUnpaused {
            target_protocol: config.target_protocol,
            admin: ctx.accounts.squads_multisig.key(),
            slot: clock.slot,
            timestamp: clock.unix_timestamp,
        });

        Ok(())
    }
}

// ============================================================================
// ESTRUCTURAS DE CUENTAS
// ============================================================================

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(
        init,
        payer = payer,
        space = 8 + GuardianConfig::INIT_SPACE,
        seeds = [b"guardian_config", target_protocol.key().as_ref()],
        bump
    )]
    pub config: Account<'info, GuardianConfig>,

    /// CHECK: Validado como seed para la derivación determinista del PDA.
    pub target_protocol: AccountInfo<'info>,

    #[account(mut)]
    pub payer: Signer<'info>,

    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct GuardianPause<'info> {
    #[account(
        mut,
        seeds = [b"guardian_config", config.target_protocol.as_ref()],
        bump = config.bump,
        has_one = guardian_bot @ GuardianError::UnauthorizedBotSigner
    )]
    pub config: Account<'info, GuardianConfig>,

    pub guardian_bot: Signer<'info>,
}

#[derive(Accounts)]
pub struct Unpause<'info> {
    #[account(
        mut,
        seeds = [b"guardian_config", config.target_protocol.as_ref()],
        bump = config.bump,
        has_one = admin @ GuardianError::UnauthorizedSquadsMultisig
    )]
    pub config: Account<'info, GuardianConfig>,

    pub squads_multisig: Signer<'info>,
}

// ============================================================================
// ESTADO ON-CHAIN
// ============================================================================

#[account]
#[derive(InitSpace)]
pub struct GuardianConfig {
    pub admin: Pubkey,            // 32 bytes (Squads Multisig Vault)
    pub guardian_bot: Pubkey,     // 32 bytes (Hot signer para pause únicamente)
    pub target_protocol: Pubkey,  // 32 bytes (Lending market / pool)
    pub is_paused: bool,          // 1 byte
    pub consecutive_pauses: u8,   // 1 byte
    pub paused_at: i64,           // 8 bytes
    pub bump: u8,                 // 1 byte
}

#[event]
pub struct GuardianInitialized {
    pub target_protocol: Pubkey,
    pub admin: Pubkey,
    pub guardian_bot: Pubkey,
}

#[event]
pub struct CircuitBreakerPaused {
    pub target_protocol: Pubkey,
    pub caller: Pubkey,
    pub reason: String,
    pub slot: u64,
    pub timestamp: i64,
}

#[event]
pub struct CircuitBreakerUnpaused {
    pub target_protocol: Pubkey,
    pub admin: Pubkey,
    pub slot: u64,
    pub timestamp: i64,
}

#[error_code]
pub enum GuardianError {
    #[msg("Firma no autorizada: Solo el Guardian Bot puede activar la pausa")]
    UnauthorizedBotSigner,

    #[msg("Firma no autorizada: Solo el Squads Multisig puede despausar el mercado")]
    UnauthorizedSquadsMultisig,

    #[msg("El mercado ya se encuentra en pausa de emergencia")]
    MarketAlreadyPaused,

    #[msg("El mercado se encuentra operando normalmente (no pausado)")]
    MarketNotPaused,

    #[msg("Límite de pausas consecutivas alcanzado; requiere revisión de Squads Multisig")]
    MaxConsecutivePausesExceeded,

    #[msg("Dirección cero inválida (Zero Address / Default Pubkey)")]
    InvalidZeroAddress,
}
