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

import { TutorialDialog } from "./TutorialDialog";
import { useTourTexts, useTutorialRunner } from "./useTutorialRunner";

/** Mounted once in the app shell: runs the tours and owns the tutorial dialog. Pages only carry anchors. */
export default function TutorialHost() {
  useTutorialRunner();
  const { values } = useTourTexts();
  return <TutorialDialog site={values?.site ?? ""} />;
}
