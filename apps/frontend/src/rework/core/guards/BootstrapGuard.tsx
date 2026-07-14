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
import BootstrapPage from "@components/pages/BootstrapPage/BootstrapPage.tsx";
import { useFrontendProperties } from "src/hooks/useFrontendProperties.ts";

export default function BootstrapGuard({ children }: PropsWithChildren) {
  // `rootBootstrapCompleted` comes from the public pre-auth config, so it is
  // known as soon as the app loads — no per-user query needed. It is a
  // durable, global marker (AUTHZ-07): once anyone completes root bootstrap
  // it is `true` forever, for every user, on this deployment.
  const { rootBootstrapCompleted } = useFrontendProperties();

  if (!rootBootstrapCompleted) {
    return <BootstrapPage />;
  }

  return <>{children}</>;
}
