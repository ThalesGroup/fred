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

//! Typed platform roles and scoped capabilities. Direct roles and effective permissions
//! are separate: permissions come only from roles held on the requested space.

use serde::{Deserialize, Serialize};

pub use fred_rust_sdk::security::platform::PlatformRole;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum PlatformPermission {
    ListAllTeams,
    DeleteTeam,
    DeleteSpace,
    RescueTeamOwner,
    EditAgentClassPath,
    ObservePlatform,
    AdministerUsers,
    ManagePlatform,
    ManageCapabilities,
    EditPlatformPrompt,
}
impl PlatformPermission {
    pub const ALL: [Self; 10] = [
        Self::ListAllTeams,
        Self::DeleteTeam,
        Self::DeleteSpace,
        Self::RescueTeamOwner,
        Self::EditAgentClassPath,
        Self::ObservePlatform,
        Self::AdministerUsers,
        Self::ManagePlatform,
        Self::ManageCapabilities,
        Self::EditPlatformPrompt,
    ];
}

/// Evaluation is a space capability, never a document read/write permission.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum SpacePermission {
    Read,
    Write,
    Manage,
    RunEvaluations,
    ManageEvaluationCorpus,
    ReadConversationsForEvaluation,
    /// Consumption aggregates on the requested team or project.
    ReadUsage,
    /// Technical administration of an organization.
    AdministerOrganization,
    CreatePersonalSpace,
}
impl SpacePermission {
    pub const ALL: [Self; 9] = [
        Self::Read,
        Self::Write,
        Self::Manage,
        Self::RunEvaluations,
        Self::ManageEvaluationCorpus,
        Self::ReadConversationsForEvaluation,
        Self::ReadUsage,
        Self::AdministerOrganization,
        Self::CreatePersonalSpace,
    ];
}
