// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";
import { useDispatch } from "react-redux";
import { useMountSessionId } from "../useOpenSessionId";
import type { UiPartRendererProps } from "../types";
import type { HtmlArtifactPartData } from "./types";
import { upsertFromPart } from "./htmlArtifactSlice";

/** Feed the preview and Files drawer without duplicating their actions in chat. */
export function HtmlArtifactCardRenderer({ part }: UiPartRendererProps) {
  const dispatch = useDispatch();
  const sessionId = useMountSessionId();
  const art = part as unknown as HtmlArtifactPartData;
  useEffect(() => {
    if (sessionId) dispatch(upsertFromPart({ sessionId, art }));
  }, [sessionId, art, dispatch]);
  return null;
}
