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

import { ProcessingGraphNode } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { Theme } from "@mui/material";

export type DocumentFlowRow = {
  document: ProcessingGraphNode;
  vectorNode?: ProcessingGraphNode;
  tableNode?: ProcessingGraphNode;
};

export type DocumentFlowRowSlice = {
  key: string;
  label: string | undefined;
  value: number;
}

export type VectorItem = number[] | Record<string, any> | string | number | null;

export type ChunkItem = {
  text?: string;
  [key: string]: any;
};

export type VectorSortMode = "name" | "vectorsDesc" | "vectorsAsc";
export type RowSortMode = "name" | "rowsDesc" | "rowsAsc";
export type LimitOption = 10 | 20 | 50 | "all";

export const distributionColors = (theme: Theme) => [
  theme.palette.primary.main,
  theme.palette.secondary.main,
  theme.palette.success.main,
  theme.palette.info.main,
  theme.palette.warning.main,
  theme.palette.error.main,
];

export interface DocumentDataPieProps {
  slices: DocumentFlowRowSlice[]
}

export interface DocumentDataRowsProps {
  rows: DocumentFlowRow[];
  search: string;
}