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

from .extract_cv import extract_cv
from .extract_enjeux_besoins import extract_enjeux_besoins
from .extract_prestation_financiere import extract_prestation_financiere
from .fill_template import fill_template

__all__ = [
    "extract_cv",
    "extract_enjeux_besoins",
    "extract_prestation_financiere",
    "fill_template",
]
