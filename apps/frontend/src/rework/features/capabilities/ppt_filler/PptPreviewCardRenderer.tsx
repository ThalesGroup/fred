// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { useMountSessionId } from "../useOpenSessionId";
import type { UiPartRendererProps } from "../types";
import type { PptPreviewPartData } from "./types";
import { registerPreview } from "./pptPreviewSlice";

/** Catalogue files are accessed in the drawer; retain preview metadata from the turn. */
export function PptPreviewCardRenderer({ part }: UiPartRendererProps) {
  const dispatch = useDispatch();
  const sessionId = useMountSessionId();
  const preview = part as unknown as PptPreviewPartData;
  useEffect(() => {
    if (sessionId) dispatch(registerPreview({ sessionId, preview }));
  }, [dispatch, sessionId, preview]);
  return null;
}
