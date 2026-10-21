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

import { type PropsWithChildren } from "react";
import BootstrapPage from "@components/pages/BootstrapPage/BootstrapPage";
import MainLayout from "@shared/layouts/MainLayout/MainLayout";
import { useOnboardingStatusQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";

/** GcuGuard owns status loading/errors and keeps this guard behind personal consent. */
export default function BootstrapGuard({ children }: PropsWithChildren) {
  const { data } = useOnboardingStatusQuery();
  if (!data) return null;
  return data.root_bootstrap_required ? (
    <MainLayout navigation={false}>
      <BootstrapPage />
    </MainLayout>
  ) : (
    <>{children}</>
  );
}
