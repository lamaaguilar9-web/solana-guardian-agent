// SPDX-License-Identifier: MIT
use anchor_lang::prelude::*;

declare_id!("Guard1anBreaker111111111111111111111111111111");

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum PauseReason {
    OracleDivergence = 0,
    OutflowVelocityExceeded = 1,
    EmergencyManual = 2,
    Other = 3,
}

#[program]
pub mod solana_guardian {
    use super::*;

    pub fn initialize(
        ctx: Context<Initialize>,
        guardian_bot: Pubkey,
        squads_multisig: Pubkey,
    ) -> Result<()> {
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

    /// Dispara la pausa de emergencia atómica optimizada (<25,000 CUs).
    pub fn guardian_pause(ctx: Context<GuardianPause>, reason: PauseReason) -> Result<()> {
        let config = &mut ctx.accounts.config;

        require!(!config.is_paused, GuardianError::MarketAlreadyPaused);
        require!(
            config.consecutive_pauses < 2,
            GuardianError::MaxConsecutivePausesExceeded
        );

        let clock = Clock::get()?;
        config.is_paused = true;
        config.consecutive_pauses = config.consecutive_pauses.saturating_add(1);
        config.paused_at = clock.unix_timestamp;

        // Invocación CPI directa sin formateo dinámico de strings en heap
        if let Some(target_program) = ctx.remaining_accounts.get(0) {
            let instruction_data: [u8; 1] = [0x01]; // Discriminador de pausa del mercado objetivo
            let account_metas = vec![AccountMeta::new(config.target_protocol, false)];
            let instruction = solana_program::instruction::Instruction {
                program_id: *target_program.key,
                accounts: account_metas,
                data: instruction_data.to_vec(),
            };
            let bump = config.bump;
            let target_key = config.target_protocol;
            let seeds = &[b"guardian_config".as_ref(), target_key.as_ref(), &[bump]];
            solana_program::program::invoke_signed(&instruction, &[target_program.clone()], &[seeds])?;
        }

        emit!(CircuitBreakerPaused {
            target_protocol: config.target_protocol,
            caller: ctx.accounts.guardian_bot.key(),
            reason_code: reason as u8,
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

#[account]
#[derive(InitSpace)]
pub struct GuardianConfig {
    pub admin: Pubkey,
    pub guardian_bot: Pubkey,
    pub target_protocol: Pubkey,
    pub is_paused: bool,
    pub consecutive_pauses: u8,
    pub paused_at: i64,
    pub bump: u8,
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
    pub reason_code: u8,
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
    #[msg("El mercado se encuentra operando normalmente")]
    MarketNotPaused,
    #[msg("Limite de pausas consecutivas alcanzado; requiere revision de Squads Multisig")]
    MaxConsecutivePausesExceeded,
}
