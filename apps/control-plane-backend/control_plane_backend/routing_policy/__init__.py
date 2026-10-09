# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Team (and personal-space) model settings (TEAM-05, #2118, extended by the
chat model and reasoning picker change).

Lets a team_admin (or a personal-space owner) choose the team's default chat
model, the models disabled for its members and the per-model reasoning
default, bounded by the ``kind="model"`` capability enablement system (#2110).
"""
