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

DB_NAME=$1
DB_USER=$2
DB_PASS=$3

PSQL_CMD="psql -U admin -h fred-postgres -d postgres"

$PSQL_CMD -c "\du" | grep "$DB_USER" || $PSQL_CMD -c "CREATE ROLE $DB_USER NOSUPERUSER LOGIN PASSWORD '$DB_PASS'"
$PSQL_CMD -c "\l" | grep -q $DB_NAME || $PSQL_CMD -c "CREATE DATABASE $DB_NAME OWNER=$DB_USER"
$PSQL_CMD -c "REVOKE ALL ON DATABASE $DB_NAME FROM PUBLIC"
$PSQL_CMD -c "GRANT CONNECT ON DATABASE $DB_NAME TO $DB_USER"