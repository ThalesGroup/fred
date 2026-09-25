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

import {
  Button,
  Checkbox,
  Dialog,
  IconButton,
  Select,
  type SelectOption,
} from "@fred-oss/ui";

const badButton = (
  // @ts-expect-error xs is intentionally unsupported by the packaged Button.
  <Button color="primary" variant="filled" size="xs">
    Bad
  </Button>
);
const badIconButton = (
  <IconButton
    variant="icon"
    // @ts-expect-error xs is intentionally unsupported by the packaged IconButton.
    size="xs"
    icon={{ type: "close" }}
    aria-label="Bad"
  />
);

const badOption: SelectOption<number> = {
  key: "bad",
  value: 1,
  label: "Bad",
  // @ts-expect-error Package options support only the approved Outlined glyph inventory.
  icon: { type: "customAgent" },
};
const badSelect = (
  <Select
    // @ts-expect-error Generic Select onChange receives the option value type, not an unrelated string.
    options={[{ key: "one", value: 1, label: "One" }]}
    size="medium"
    onChange={(value: string) => value}
  />
);
const badDialog = (
  // @ts-expect-error Action-oriented Dialog requires a caller-owned confirm label.
  <Dialog open title="Bad" onConfirm={() => {}} onCancel={() => {}}>
    Bad
  </Dialog>
);
const badCheckbox = (
  // @ts-expect-error Native checked state is Boolean.
  <Checkbox checked="yes" />
);

export {
  badButton,
  badIconButton,
  badOption,
  badSelect,
  badDialog,
  badCheckbox,
};
