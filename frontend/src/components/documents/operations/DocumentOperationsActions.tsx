// Copyright Thales 2025
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

import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";
import { TFunction } from "i18next";
import { DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { CustomRowAction } from "./DocumentOperationsTableRowActionsMenu";
import { CustomBulkAction } from "./DocumentOperationsTableSelectionToolbar";

export const createProcessAction = (
  onProcess: (file: DocumentMetadata) => Promise<void>,
  t: TFunction,
): CustomRowAction => ({
  icon: <RocketLaunchIcon />,
  name: t("documentActions.process"),
  handler: onProcess,
});
export const createScheduleAction = (
  onSchedule: (file: DocumentMetadata) => Promise<void>,
  t: TFunction,
): CustomRowAction => ({
  icon: <RocketLaunchIcon />,
  name: t("documentActions.schedule"),
  handler: onSchedule,
});

export const createBulkProcessSyncAction = (
  onBulkProcess: (files: DocumentMetadata[]) => Promise<void>,
  t: TFunction,
): CustomBulkAction => ({
  icon: <RocketLaunchIcon />,
  name: t("documentTable.processSelected"),
  handler: onBulkProcess,
});
export const createBulkScheduleAction = (
  onBulkSchedule: (files: DocumentMetadata[]) => Promise<void>,
  t: TFunction,
): CustomBulkAction => ({
  icon: <RocketLaunchIcon />,
  name: t("documentTable.scheduleSelected"),
  handler: onBulkSchedule,
});
