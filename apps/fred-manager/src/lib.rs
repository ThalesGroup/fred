//! fred-manager: ownership of spaces, folders and documents, their authorization,
//! and submission of ingestion work to the Python workers.

pub mod api;
pub mod auth;
pub mod bootstrap;
pub mod config;
pub mod db;
pub mod domain;
pub mod error;
pub mod fga;
pub mod ingestion;
pub mod spaces;
