# Copyright Thales 2025
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

"""One-shot kea -> swift migration export/import.

This package is deliberately scoped to the *kea* main branch (which is slated
for removal). It produces a self-contained snapshot bundle of the platform's
durable state so it can be downloaded from production and replayed into another
kea (Phase 1) or transformed into swift's schema (Phase 2, implemented later on
the swift branch). See ``docs/swift/ops/MIGRATION-CASTLE-TO-S3NS.html``.
"""
