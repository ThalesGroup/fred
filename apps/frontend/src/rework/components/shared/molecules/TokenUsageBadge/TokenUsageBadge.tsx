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

import type { TokenUsage } from "@rework/types/conversation";
import styles from "./TokenUsageBadge.module.css";

interface TokenUsageBadgeProps {
  usage: TokenUsage;
}

export function TokenUsageBadge({ usage }: TokenUsageBadgeProps) {
  return (
    <div className={styles.root}>
      <span className={styles.segment}>↑{usage.input_tokens.toLocaleString()}</span>
      <span className={styles.sep}>·</span>
      <span className={styles.segment}>↓{usage.output_tokens.toLocaleString()}</span>
      <span className={styles.sep}>·</span>
      <span className={styles.total}>{usage.total_tokens.toLocaleString()} tokens</span>
    </div>
  );
}
