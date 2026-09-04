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
Platform-wide platform prompt: the first block of every composed system prompt.

Why this package exists:
- one org-admin-editable text applies ahead of every agent's own
  template. It is stored as a single control-plane row and delivered to the
  runtime per turn on `BoundRuntimeContext.platform_prompt`, exactly like
  `platform_chat_model_binding`.

How to use it:
- `store.py` is pure CRUD, `service.py` owns authorization, `api.py` exposes
  the two admin routes.
"""
