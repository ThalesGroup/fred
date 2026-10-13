//! One-time root platform-admin bootstrap, ported from control-plane `bootstrap/service.py`.
//! Two independent proofs (a verified bearer and the deploy-time secret), self-promotion
//! only, and a durable marker so removing every admin later never reopens it.

use sqlx::PgPool;

use crate::{error::AppError, fga::Fga};

const MIN_TOKEN_LENGTH: usize = 16;
/// `advisory_lock_key("fred-manager.platform_bootstrap")`, as fred-core derives it.
const LOCK_KEY: i64 = -1609067376650834247;

pub const INVALID: &str = "Invalid or disabled bootstrap secret.";
pub const COMPLETED: &str = "Root bootstrap already completed — this endpoint is permanently \
     disabled. Recovering from a lost platform_admin is a separate break-glass procedure, \
     not a reopening of root bootstrap.";
pub const AUTH_DISABLED: &str = "Authentication is disabled in this deployment — root \
     bootstrap cannot run without real Keycloak/OIDC validation. Enable authentication \
     before retrying.";

/// The secret comes from the environment only: config/.env locally, a Secret on k3d.
pub fn configured_token(env_var: Option<&str>) -> Option<String> {
    usable(&std::env::var(env_var?).ok()?)
}

/// Shorter secrets, including blank ones, count as not configured.
fn usable(value: &str) -> Option<String> {
    let value = value.trim();
    (value.chars().count() >= MIN_TOKEN_LENGTH).then(|| value.to_string())
}

/// `secrets.compare_digest`: the time taken does not depend on where the inputs differ.
pub fn same_secret(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

/// Grants platform admin to `uid`, the caller's own subject. The tuple is written before
/// the marker, under a transaction-scoped advisory lock: a failure in between leaves a
/// retryable state, never a burnt bootstrap with no admin.
pub async fn grant_root(pool: &PgPool, fga: &Fga, uid: &str) -> Result<(), AppError> {
    let mut tx = pool.begin().await?;
    sqlx::query("select pg_advisory_xact_lock($1)")
        .bind(LOCK_KEY)
        .execute(&mut *tx)
        .await?;
    let done: bool = sqlx::query_scalar("select exists(select 1 from platform_bootstrap)")
        .fetch_one(&mut *tx)
        .await?;
    if done {
        return Err(AppError::Conflict(COMPLETED.into()));
    }
    fga.grant_platform_admin(uid).await?;
    sqlx::query("insert into platform_bootstrap (completed_by) values ($1)")
        .bind(uid)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn secret_comparison() {
        assert!(same_secret("0123456789abcdef", "0123456789abcdef"));
        assert!(!same_secret("0123456789abcdef", "0123456789abcdeX"));
        assert!(!same_secret("0123456789abcdef", "0123456789abcde"));
    }

    #[test]
    fn token_source() {
        assert_eq!(configured_token(None), None);
        assert_eq!(
            configured_token(Some("FRED_MANAGER_TEST_UNSET_TOKEN")),
            None
        );
        assert_eq!(
            usable("  0123456789abcdef0123\n").as_deref(),
            Some("0123456789abcdef0123")
        );
        assert_eq!(usable("too-short"), None);
        assert_eq!(usable("                    "), None);
    }
}
