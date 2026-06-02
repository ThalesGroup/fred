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

from typing import Any, Dict, List, Literal

from fred_core.common import OwnerFilter
from pydantic import BaseModel


class SetDatasetRequest(BaseModel):
    """
    Select one tabular dataset for stateful statistics operations.

    Why this exists:
    - The statistics feature keeps one loaded pandas DataFrame in memory and
      needs the same area/library scope contract as the tabular API.

    How to use:
    - Send the target `document_uid`.
    - Optionally pass `owner_filter`, `team_id`, and
      `document_library_tags_ids` to keep selection inside the active scope.
    """

    document_uid: str
    document_library_tags_ids: list[str] | None = None
    owner_filter: OwnerFilter | None = None
    team_id: str | None = None


class DetectOutliersRequest(BaseModel):
    method: Literal["zscore", "iqr"] = "zscore"
    threshold: float = 3.0


class DetectOutliersMLRequest(BaseModel):
    features: List[str]
    method: Literal["isolation_forest", "lof"] = "isolation_forest"


class PCARequest(BaseModel):
    features: List[str]
    n_components: int = 2


class PlotHistogramRequest(BaseModel):
    column: str
    bins: int = 30


class PlotScatterRequest(BaseModel):
    x_col: str
    y_col: str


class TrainModelRequest(BaseModel):
    target: str
    features: List[str]
    model_type: Literal["linear", "random_forest"] = "linear"


class PredictRowRequest(BaseModel):
    row: Dict[str, Any]


class SaveModelRequest(BaseModel):
    name: str


class LoadModelRequest(BaseModel):
    name: str
