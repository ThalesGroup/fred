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

export type ChatAttachmentStatus = "uploading" | "ready" | "ingesting" | "error";

export interface ChatImageContext {
  name: string;
  mime: string;
  size: number;
  dataUrl: string;
}

export interface ChatAttachment {
  id: string;
  name: string;
  size: number;
  mime: string;
  status: ChatAttachmentStatus;
  isImage: boolean;
  documentUid?: string;
  workspacePath?: string;
  imageContext?: ChatImageContext;
  taskIds: string[];
  error?: string;
}

export interface SessionAttachment {
  attachmentId: string;
  name: string;
  mime?: string;
  sizeBytes?: number;
  summaryMd: string;
  documentUid?: string;
  storageKey?: string;
  workspacePath?: string;
  createdAt?: string;
  updatedAt?: string;
}
