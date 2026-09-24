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

"""Document capabilities over the Knowledge Flow ports.

One subpackage per capability, each registered as its own `fred.capabilities`
entry point in `pyproject.toml`. `document_read_common` is the one shared
module: config, pagination and error shaping the reading pair and
`document_similarity` have in common.
"""
