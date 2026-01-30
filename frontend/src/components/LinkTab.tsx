// Copyright Thales 2025
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

import * as React from "react";
import Tab from "@mui/material/Tab";
import { Link, useLocation } from "react-router-dom";

function samePageLinkNavigation(
  event: React.MouseEvent<HTMLAnchorElement, MouseEvent>,
) {
  if (
    event.defaultPrevented ||
    event.button !== 0 || // ignore everything but left-click
    event.metaKey ||
    event.ctrlKey ||
    event.altKey ||
    event.shiftKey
  ) {
    return false;
  }
  return true;
}

interface LinkTabProps {
  label?: string;
  to: string;
}

export function LinkTab(props: LinkTabProps) {
  const { to, ...tabProps } = props;
  const location = useLocation();
  const selected = location.pathname === to;

  return (
    <Tab
      component={Link}
      to={to}
      onClick={(event: React.MouseEvent<HTMLAnchorElement, MouseEvent>) => {
        if (!samePageLinkNavigation(event)) {
          event.preventDefault();
        }
      }}
      aria-current={selected ? "page" : undefined}
      {...tabProps}
    />
  );
}
