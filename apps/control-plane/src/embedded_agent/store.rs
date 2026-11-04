// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Rig's opaque log, owned by the corresponding conversation. No runtime schema access.

use std::io;

use rig_memory::{AsyncStore, LogWriteError};
use sqlx::PgPool;
use uuid::Uuid;

#[derive(Clone)]
pub struct ConversationStore(pub PgPool);

fn session_id(name: &str) -> io::Result<Uuid> {
    Uuid::parse_str(name).map_err(|error| io::Error::new(io::ErrorKind::InvalidInput, error))
}

impl ConversationStore {
    async fn write(
        &self,
        name: &str,
        len: u64,
        bytes: &[u8],
        append: bool,
    ) -> Result<(), LogWriteError> {
        let id = session_id(name)?;
        let len = i64::try_from(len)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidInput, error))?;
        // The first writer may create a log only at length zero. ON CONFLICT checks
        // the latest row under its write lock, including concurrent first writers.
        let result = if len == 0 {
            sqlx::query(
                "insert into embedded_agent_conversation(session_id,log) values($1,$2)
                 on conflict(session_id) do update set log=excluded.log
                 where octet_length(embedded_agent_conversation.log)=0",
            )
            .bind(id)
            .bind(bytes)
            .execute(&self.0)
            .await
        } else {
            sqlx::query(
                "update embedded_agent_conversation
                 set log=case when $4 then log || $2 else $2 end
                 where session_id=$1 and octet_length(log)=$3",
            )
            .bind(id)
            .bind(bytes)
            .bind(len)
            .bind(append)
            .execute(&self.0)
            .await
        }
        .map_err(io::Error::other)?;
        if result.rows_affected() == 0 {
            return Err(LogWriteError::Changed);
        }
        Ok(())
    }
}

impl AsyncStore for ConversationStore {
    async fn read_log_async(&self, name: &str) -> io::Result<Vec<u8>> {
        sqlx::query_scalar("select log from embedded_agent_conversation where session_id=$1")
            .bind(session_id(name)?)
            .fetch_optional(&self.0)
            .await
            .map_err(io::Error::other)?
            .ok_or_else(|| io::ErrorKind::NotFound.into())
    }

    async fn append_log_async(
        &self,
        name: &str,
        len: u64,
        bytes: &[u8],
    ) -> Result<(), LogWriteError> {
        self.write(name, len, bytes, true).await
    }

    async fn replace_log_async(
        &self,
        name: &str,
        len: u64,
        bytes: &[u8],
    ) -> Result<(), LogWriteError> {
        self.write(name, len, bytes, false).await
    }

    async fn read_file_async(&self, name: &str) -> io::Result<Vec<u8>> {
        rig_memory::check_name(name)?;
        Err(io::ErrorKind::Unsupported.into())
    }

    async fn write_file_async(&self, name: &str, _bytes: &[u8]) -> io::Result<()> {
        rig_memory::check_name(name)?;
        Err(io::ErrorKind::Unsupported.into())
    }
}
