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

import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import styles from "./AgentChatButton.module.scss";

interface AgentChatButtonProps {
  /** Chat route. Without it the button shows disabled. */
  to?: string;
  "aria-label"?: string;
}

/** The agent card's "Chat" button, spectrum border on hover; shared with the home page. */
export default function AgentChatButton({ to, "aria-label": ariaLabel }: AgentChatButtonProps) {
  const { t } = useTranslation();
  const button = (
    <Button
      color="primary"
      variant="outlined"
      size="medium"
      icon={{ category: "outlined", type: "reviews" }}
      className={styles.chatButton}
      disabled={!to}
    >
      {t("rework.agentCard.chat")}
    </Button>
  );
  return to ? (
    <Link to={to} className={styles.chatLink} aria-label={ariaLabel}>
      {button}
    </Link>
  ) : (
    button
  );
}
