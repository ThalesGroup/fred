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
  const result = controlPlaneApi.endpoints["getUserDetailsControlPlaneV1UserGet"].useQuery(undefined);

  if (result.isLoading || result.isUninitialized) {
    const fetchUserDetailsAction = controlPlaneApi.endpoints["getUserDetailsControlPlaneV1UserGet"].initiate(undefined);
    throw dispatch(fetchUserDetailsAction as any);
  }
  const userDetails: UserDetails = result.data;

  if (!gcuVersion || (userDetails?.cguValidated != null && userDetails.cguValidated.toString() === gcuVersion)) {
    return <>{children}</>;
  }

  return <GcuPage />;
}
