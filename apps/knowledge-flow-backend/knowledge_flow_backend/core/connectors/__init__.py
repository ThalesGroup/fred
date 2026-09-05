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
Concrete `fred_sdk.contracts.connector.SourceConnector` implementations for
pull-mode Corpus sources (docs/swift/rfc/INDEXED-CORPUS-RFC.md).

This package is deliberately separate from the deleted `core/stores/content/`
loader hierarchy: a connector here owns only discover/fetch against one
external source, never storage, cataloging, or scheduling.
"""
