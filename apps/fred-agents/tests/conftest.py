# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Share fred-runtime's Weaver turn fixtures: pod tools run only inside an admitted turn."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "libs" / "fred-runtime" / "tests"))
