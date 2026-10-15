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
//! are separate: a computed grant must never be presented as a deletable tuple.

use serde::{Deserialize, Serialize};

#[derive(
    Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, utoipa::ToSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum PlatformRole {
    PlatformAdmin,
    PlatformObserver,
    TeamManager,
    FeatureManager,
    PromptEditor,
}
impl PlatformRole {
    pub const ALL: [Self; 5] = [
        Self::PlatformAdmin,
        Self::PlatformObserver,
        Self::TeamManager,
        Self::FeatureManager,
        Self::PromptEditor,
    ];
    pub fn relation(self) -> &'static str {
        match self {
            Self::PlatformAdmin => "admin",
            Self::PlatformObserver => "observer",
            Self::TeamManager => "team_manager",
            Self::FeatureManager => "feature_manager",
            Self::PromptEditor => "prompt_editor",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "platform_admin" | "admin" => Some(Self::PlatformAdmin),
            "platform_observer" | "observer" => Some(Self::PlatformObserver),
            "team_manager" => Some(Self::TeamManager),
            "feature_manager" => Some(Self::FeatureManager),
            "prompt_editor" => Some(Self::PromptEditor),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum PlatformPermission {
    CreateTeam,
    ListAllTeams,
    DeleteTeam,
    RescueTeamAdmin,
    EditAgentClassPath,
    ObservePlatform,
    AdministerUsers,
    ManagePlatform,
    ManageCapabilities,
    EditPlatformPrompt,
}
impl PlatformPermission {
    pub const ALL: [Self; 10] = [
        Self::CreateTeam,
        Self::ListAllTeams,
        Self::DeleteTeam,
        Self::RescueTeamAdmin,
        Self::EditAgentClassPath,
        Self::ObservePlatform,
        Self::AdministerUsers,
        Self::ManagePlatform,
        Self::ManageCapabilities,
        Self::EditPlatformPrompt,
    ];
    pub fn relation(self) -> &'static str {
        match self {
            Self::CreateTeam => "can_create_team",
            Self::ListAllTeams => "can_list_all_teams",
            Self::DeleteTeam => "can_delete_team",
            Self::RescueTeamAdmin => "can_rescue_team_admin",
            Self::EditAgentClassPath => "can_edit_agent_class_path",
            Self::ObservePlatform => "can_observe_platform",
            Self::AdministerUsers => "can_administer_users",
            Self::ManagePlatform => "can_manage_platform",
            Self::ManageCapabilities => "can_manage_capabilities",
            Self::EditPlatformPrompt => "can_edit_platform_prompt",
        }
    }
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
}
impl SpacePermission {
    pub const ALL: [Self; 6] = [
        Self::Read,
        Self::Write,
        Self::Manage,
        Self::RunEvaluations,
        Self::ManageEvaluationCorpus,
        Self::ReadConversationsForEvaluation,
    ];
    pub fn relation(self) -> &'static str {
        match self {
            Self::Read => "can_read",
            Self::Write => "can_write",
            Self::Manage => "can_manage",
            Self::RunEvaluations => "can_run_evaluations",
            Self::ManageEvaluationCorpus => "can_manage_evaluation_corpus",
            Self::ReadConversationsForEvaluation => "can_read_conversations_for_evaluation",
        }
    }
}
