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

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.from datetime import datetime

from common.structure import Series
from common.utils import auc_calculation
from app.services.finops.structure import CloudBilling


# Parse CloudBilling data to Series
def cloud_billings_to_series(cloud_billings: list[CloudBilling]) -> Series:
    """
    Parse the consumption data to the response format
    """
    timestamps: list[datetime] = []
    values: list[float] = []
    unit = cloud_billings[0].unit if len(cloud_billings) > 0 else ""

    for cloud_billing in cloud_billings:
        timestamps.append(cloud_billing.start)
        values.append(cloud_billing.value)

    return Series(
        timestamps=timestamps,
        values=values,
        auc=auc_calculation(values),
        unit=unit
    )
