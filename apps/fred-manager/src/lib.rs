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

//! fred-manager: space governance, folder operations, document metadata reads
//! and deferred space cleanup with its dedicated Temporal worker.

pub mod api;
pub mod auth;
pub mod bootstrap;
pub mod config;
pub mod db;
pub mod documents;
pub mod domain;
pub mod error;
pub mod fga;
pub mod keycloak;
pub mod lifecycle;
pub mod logging;
pub mod onboarding;
pub mod platform;
pub mod roles;
pub mod spaces;

pub mod provisioning;

pub mod blueprint;
