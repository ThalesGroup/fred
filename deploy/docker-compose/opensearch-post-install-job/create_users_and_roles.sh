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

#!/usr/bin/env bash

while ! /usr/share/opensearch/plugins/opensearch-security/tools/securityadmin.sh \
    --accept-red-cluster \
    --configdir /usr/share/opensearch/config/opensearch-security/ \
    --ignore-clustername \
    --disable-host-name-verification \
    --hostname fred-opensearch \
    --port 9200 \
    -cacert /usr/share/opensearch/config/certs/ca.crt \
    -cert /usr/share/opensearch/config/certs/admin.crt \
    -key /usr/share/opensearch/config/certs/admin.key
do
    sleep 5
done
