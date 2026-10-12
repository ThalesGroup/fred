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

import { MarkdownRenderer } from "../MarkdownRenderer/MarkdownRenderer";
import styles from "./PatchNoteBody.module.css";

/** A patch note's rendered markdown, as users read it: the dialog and the editor preview share it. */
export function PatchNoteBody({ markdown }: { markdown: string }) {
  return (
    <div className={styles.body}>
      <MarkdownRenderer text={markdown} fullWidth linksInNewTab />
    </div>
  );
}

export default PatchNoteBody;
