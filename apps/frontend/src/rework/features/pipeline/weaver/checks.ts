// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { managerActor } from "../../imports/managerImportRun";
import type { ApiDispatch, ApiRead } from "../deps/api";
import type { MySpace } from "../../../../slices/controlPlane/controlPlaneOpenApi";

export interface WeaverChecks {
  dispatch: ApiDispatch;
  read: ApiRead;
  userId: string;
  spaceId: string;
  spaceKind?: MySpace["kind"];
  organizationId: string;
}

/** A run and its cleanup may outlive the page that started them. */
export function bindRunDispatch(dispatch: ApiDispatch, actor = managerActor()): ApiDispatch {
  const guarded: ApiDispatch = (action) => {
    if (managerActor() !== actor) throw new Error("The signed-in account changed during this run.");
    return dispatch(action);
  };
  return guarded;
}
