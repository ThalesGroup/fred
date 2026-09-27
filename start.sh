#!/bin/bash
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


# Stop all subprocesses when the script receives Ctrl+C
trap "echo 'Stopping...'; kill 0" SIGINT

# agentic backend
(cd apps/control-plane-backend && make run 2>&1 | sed "s/^/[CONTROL-PLANE] /") &

# agentic backend
(cd agentic-backend && make run 2>&1 | sed "s/^/[AGENTIC] /") &

# knowledge-flow backend
(cd apps/knowledge-flow-backend && make run 2>&1 | sed "s/^/[KF] /") &

# frontend
(cd apps/frontend && make run 2>&1 | sed "s/^/[FRONTEND] /") &

# wait for all background jobs
wait
