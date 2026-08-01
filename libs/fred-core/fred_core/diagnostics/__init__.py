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
fred_core.diagnostics — cross-platform runtime diagnostics for Fred pods.

Exports
-------
    from fred_core.diagnostics import (
        install_gc_diagnostics,
        collect_and_trim,
        collect_and_report_types,
        current_rss_kb,
        malloc_trim,
        GCDiagnosticsHandle,
        GCTrimResult,
        GCTypeReport,
    )
"""

from .gc_diagnostics import (
    DEFAULT_INTERVAL_ENV_VAR,
    GCDiagnosticsHandle,
    GCTrimResult,
    GCTypeReport,
    collect_and_report_types,
    collect_and_trim,
    current_rss_kb,
    install_gc_diagnostics,
    malloc_trim,
)

__all__ = [
    "DEFAULT_INTERVAL_ENV_VAR",
    "GCDiagnosticsHandle",
    "GCTrimResult",
    "GCTypeReport",
    "collect_and_report_types",
    "collect_and_trim",
    "current_rss_kb",
    "install_gc_diagnostics",
    "malloc_trim",
]
