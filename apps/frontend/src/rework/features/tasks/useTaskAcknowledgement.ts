// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useDispatch } from "react-redux";
import { taskAcknowledged } from "./taskSlice";

/** Browser-only activities have no server task record. Durable upload receipts
 * are acknowledged by the Control Plane import controller. */
export function useTaskAcknowledgement() {
  const dispatch = useDispatch();
  const acknowledge = async (taskId: string, _kind: string | null, _localOnly?: boolean) => {
    dispatch(taskAcknowledged({ taskId, acknowledgedAt: new Date().toISOString() }));
  };
  return { acknowledge, isAcknowledging: (_taskId: string) => false };
}
