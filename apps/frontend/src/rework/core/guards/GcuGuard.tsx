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

import { PropsWithChildren } from "react";
import GcuPage from "@components/pages/GcuPage/GcuPage.tsx";
import { controlPlaneApi } from "../../../slices/controlPlane/controlPlaneApi.ts";
import { useDispatch } from "react-redux";
import { UserDetails } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { useFrontendProperties } from "src/hooks/useFrontendProperties.ts";

export default function GcuGuard({ children }: PropsWithChildren) {
  const { gcuVersion } = useFrontendProperties();
  const dispatch = useDispatch();
  // `gcuVersion` comes from the public pre-auth config, so it is known even
  // before the user has accepted. When it is null, CGU gating is off for this
  // deployment (standalone / auth disabled / no version configured): skip the
  // user-details query entirely and let the app render — no acceptance screen.
  const result = controlPlaneApi.endpoints["getUserDetailsControlPlaneV1UserGet"].useQuery(undefined, {
    skip: !gcuVersion,
  });

  if (!gcuVersion) {
    return <>{children}</>;
  }

  if (result.isLoading || result.isUninitialized) {
    const fetchUserDetailsAction = controlPlaneApi.endpoints["getUserDetailsControlPlaneV1UserGet"].initiate(undefined);
    throw dispatch(fetchUserDetailsAction as unknown as Parameters<typeof dispatch>[0]);
  }
  const userDetails: UserDetails = result.data;

  // CGU is required: render the app only once the persisted accepted version
  // matches the active one; otherwise route to the acceptance page. The user
  // query uses `get_current_user_without_gcu`, so it stays reachable even while
  // the GCU-gated bootstrap is 403-ing.
  if (userDetails?.cguValidated != null && userDetails.cguValidated.toString() === gcuVersion) {
    return <>{children}</>;
  }

  return <GcuPage />;
}
