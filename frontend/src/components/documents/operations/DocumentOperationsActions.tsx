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

import DeleteIcon from "@mui/icons-material/Delete";
import DownloadIcon from "@mui/icons-material/Download";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";
import VisibilityIcon from "@mui/icons-material/Visibility";
import { TFunction } from "i18next";
import { DocumentMetadata } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { CustomRowAction } from "./DocumentOperationsTableRowActionsMenu";
import { CustomBulkAction } from "./DocumentOperationsTableSelectionToolbar";

// Individual action creators that parent components can use
export const createPreviewAction = (
  onOpen: (file: DocumentMetadata) => Promise<void>,
  t: TFunction,
): CustomRowAction => ({
  icon: <VisibilityIcon />,
  name: t("documentActions.preview"),
  handler: onOpen,
});

export const createDownloadAction = (
  onDownload: (file: DocumentMetadata) => Promise<void>,
  t: TFunction,
): CustomRowAction => ({
  icon: <DownloadIcon />,
  name: t("documentActions.download"),
  handler: onDownload,
});

export const createDeleteAction = (
  onDelete: (file: DocumentMetadata) => Promise<void>,
  t: TFunction,
): CustomRowAction => ({
  icon: <DeleteIcon />,
  name: t("documentActions.delete"),
  handler: onDelete,
});

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

// Bulk action creators
export const createBulkDeleteAction = (
  onBulkDelete: (files: DocumentMetadata[]) => Promise<void>,
  t: TFunction,
): CustomBulkAction => ({
  icon: <DeleteIcon />,
  name: t("documentTable.deleteSelected"),
  handler: onBulkDelete,
});

export const createBulkDownloadAction = (
  onBulkDownload: (files: DocumentMetadata[]) => Promise<void>,
  t: TFunction,
): CustomBulkAction => ({
  icon: <DownloadIcon />,
  name: t("documentTable.downloadSelected"),
  handler: onBulkDownload,
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

