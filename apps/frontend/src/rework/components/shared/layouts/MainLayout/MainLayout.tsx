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

import { useCallback } from "react";
import { useDispatch } from "react-redux";
import { Outlet } from "react-router-dom";
import type { ThunkDispatch, UnknownAction } from "@reduxjs/toolkit";
import Sidebar from "@shared/layouts/Sidebar/Sidebar.tsx";
import TeamMemberGate from "@shared/organisms/TeamMemberGate/TeamMemberGate.tsx";
import TeamAdminCharterGate from "@shared/organisms/TeamAdminCharterGate/TeamAdminCharterGate.tsx";
import { useTaskPolling } from "../../../../features/tasks/useTaskPolling.ts";
import { useTaskRehydration } from "../../../../features/tasks/useTaskRehydration.ts";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { controlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./MainLayout.module.css";

/** A bootstrap fetched this recently is fresh enough on focus. */
const BOOTSTRAP_FOCUS_MAX_AGE_S = 30;

export default function MainLayout() {
  // Another session can add or remove the caller from a team: catch up on return.
  const dispatch = useDispatch<ThunkDispatch<unknown, unknown, UnknownAction>>();
  const refreshBootstrap = useCallback(
    () =>
      dispatch(
        controlPlaneApi.endpoints.getFrontendBootstrapControlPlaneV1FrontendBootstrapGet.initiate(undefined, {
          subscribe: false,
          forceRefetch: BOOTSTRAP_FOCUS_MAX_AGE_S,
        }),
      ),
    [dispatch],
  );
  useRefetchOnWindowFocus(refreshBootstrap, false);
  useTaskRehydration();
  useTaskPolling();
  return (
    <div className={styles.mainLayout}>
      <nav className={styles.sidebar}>
        <Sidebar />
      </nav>
      <main className={styles.content}>
        <TeamMemberGate>
          <TeamAdminCharterGate>
            <Outlet />
          </TeamAdminCharterGate>
        </TeamMemberGate>
      </main>
    </div>
  );
}
