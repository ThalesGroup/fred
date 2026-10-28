// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! control-plane: organizations, teams, projects and personal spaces with their roles,
//! folders, original documents and their processing, provisioning import and deferred
//! space cleanup.

/// Receipts are keyed by kind and ID: a session ID is client-chosen and may
/// equal a space ID, so every space lookup by target ID applies this filter.
macro_rules! space_target {
    () => {
        "target_kind in ('organization', 'team', 'project')"
    };
}

pub mod agent_instances;
pub mod agents;
pub mod api;
pub mod auth;
pub mod bootstrap;
pub mod config;
pub mod db;
pub mod documents;
pub mod domain;
pub mod embedded_agent;
pub mod error;
pub mod extract;
pub mod fga;
pub mod keycloak;
pub mod lifecycle;
pub mod logging;
pub mod model_catalog;
pub mod onboarding;
pub mod platform;
pub mod processing;
pub mod roles;
pub mod sessions;
pub mod spaces;
pub mod supervision;
pub mod user_preferences;
pub mod users;

pub mod provisioning;

pub mod blueprint;
