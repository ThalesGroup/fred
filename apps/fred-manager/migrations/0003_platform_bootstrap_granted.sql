-- Copyright Thales 2026
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- A claimed bootstrap (`completed_by`) is finished only once its grant is recorded:
-- null means the OpenFGA write may not have happened, and only the claimant may retry.
-- Existing markers count as finished, so an earlier bootstrap stays closed.
alter table platform_bootstrap add column granted_at timestamptz;
update platform_bootstrap set granted_at = completed_at;
