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

import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Button,
  Checkbox,
  Chip,
  Dialog,
  Icon,
  IconButton,
  Select,
  Spinner,
  TextInput,
  Tooltip,
} from "@fred-oss/ui";
import type {
  ButtonProps,
  ButtonSize,
  ButtonVariant,
  CheckboxProps,
  ChipProps,
  ColorTheme,
  IconButtonProps,
  IconButtonVariant,
  IconProps,
  DialogProps,
  MaterialIconType,
  SelectOption,
  SelectProps,
  SpinnerProps,
  TextInputProps,
  TooltipProps,
} from "@fred-oss/ui";
import "@fred-oss/design-tokens/tokens.css";
import "@fred-oss/ui/styles.css";
import "./consumer.css";

const reviewedIcon: MaterialIconType = "search";
const typedIcon: IconProps = {
  type: reviewedIcon,
  accessibleName: "Search symbol",
};
const buttonSize: ButtonSize = "medium";
const buttonVariant: ButtonVariant = "filled";
const buttonColor: ColorTheme = "primary";
const typedButton: ButtonProps = {
  color: buttonColor,
  variant: buttonVariant,
  size: buttonSize,
  children: "Save",
};
const iconButtonVariant: IconButtonVariant = "outlined";
const typedIconButton: IconButtonProps = {
  color: "secondary",
  variant: iconButtonVariant,
  size: "small",
  icon: { type: "add" },
  "aria-label": "Add item",
};
const typedInput: TextInputProps = { label: "Project name", maxLength: 12 };
const typedSpinner: SpinnerProps = { statusText: "Saving package" };
const typedCheckbox: CheckboxProps = { "aria-label": "Accept terms" };
const typedChip: ChipProps = { label: "Draft", tone: "default" };
const typedTooltip: TooltipProps = {
  text: "More details",
  children: <button type="button">Hint trigger</button>,
};
const options: SelectOption<string>[] = [
  {
    key: "team:alpha",
    value: "first",
    label: "First",
    icon: { type: "check" },
  },
  { key: "disabled", value: "disabled", label: "Unavailable", disabled: true },
  { key: "team.alpha", value: "second", label: "Second" },
];

function App() {
  const [clicks, setClicks] = useState(0);
  const [name, setName] = useState("Fred");
  const [resetCount, setResetCount] = useState(0);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selection, setSelection] = useState<string | undefined>(undefined);
  const [dialogSelection, setDialogSelection] = useState<string | undefined>(
    undefined,
  );
  const [chipRemoved, setChipRemoved] = useState(false);
  const [checkboxChecked, setCheckboxChecked] = useState(false);
  const typedSelect: SelectProps<string> = {
    options,
    value: selection,
    onChange: setSelection,
    size: "medium",
    label: "Choose option",
  };
  const typedDialog: Omit<DialogProps, "children"> = {
    open: dialogOpen,
    title: "Confirm choice",
    confirmLabel: "Apply",
    onConfirm: () => setDialogOpen(false),
    onCancel: () => setDialogOpen(false),
  };
  return (
    <main className="fred-ui consumer-shell" data-clicks={clicks}>
      <h1>FRED UI archive consumer</h1>
      <section aria-label="Public components">
        <Button
          {...typedButton}
          className="consumer-button"
          onClick={() => setClicks((value) => value + 1)}
        >
          Save {clicks}
        </Button>
        <Button
          color="secondary"
          variant="outlined"
          size="small"
          disabled
          onClick={() => setClicks((value) => value + 1)}
        >
          Disabled action
        </Button>
        <IconButton
          {...typedIconButton}
          className="consumer-icon-button"
          onClick={() => setClicks((value) => value + 1)}
        />
        <Icon {...typedIcon} />
        <Icon type="info" />
        <TextInput
          {...typedInput}
          id="project-name"
          value={name}
          onChange={(event) => setName(event.currentTarget.value)}
          explanation="Use a short name"
        />
        <TextInput
          id="invalid-name"
          label="Invalid name"
          error="A name is required"
          defaultValue=""
        />
        <TextInput
          id="disabled-name"
          label="Disabled name"
          disabled
          defaultValue="Locked"
        />
        <Spinner />
        <Spinner {...typedSpinner} />
        <Spinner decorative />
        <IconButton
          variant="filled"
          size="medium"
          icon={{ type: "download" }}
          aria-label="Downloading"
          loading
        />
        <IconButton
          className="consumer-tonal-on-surface"
          color="on-surface"
          variant="tonal"
          size="small"
          icon={{ type: "visibility" }}
          aria-label="Surface tonal"
        />
        <IconButton
          className="consumer-tonal-on-surface-retreat"
          color="on-surface-retreat"
          variant="tonal"
          size="small"
          icon={{ type: "info" }}
          aria-label="Retreat tonal"
        />
        <form
          aria-label="Reset counter fixture"
          data-reset-count={resetCount}
          onReset={() => setResetCount((count) => count + 1)}
        >
          <TextInput
            id="reset-name"
            label="Resettable name"
            defaultValue="abc"
            maxLength={20}
          />
          <button type="reset">Reset counter</button>
        </form>
        <section aria-label="Extended public components">
          <Select {...typedSelect} />
          <Select
            options={[]}
            size="small"
            onChange={() => {}}
            ariaLabel="Empty selection"
            emptyMessage="No choices available"
          />
          <Select
            options={[
              {
                key: "disabled-only",
                value: "disabled-only",
                label: "Unavailable",
                disabled: true,
              },
            ]}
            size="small"
            onChange={() => {}}
            ariaLabel="Disabled selection"
            emptyMessage="No enabled choices"
          />
          {!chipRemoved && (
            <Chip
              {...typedChip}
              secondary="Ready"
              leading={<Icon type="info" />}
              onRemove={() => setChipRemoved(true)}
            />
          )}
          <Tooltip {...typedTooltip} />
          <Checkbox
            {...typedCheckbox}
            checked={checkboxChecked}
            onChange={(event) =>
              setCheckboxChecked(event.currentTarget.checked)
            }
          />
          <Checkbox aria-label="Disabled choice" disabled />
          <Checkbox aria-label="Partial choice" indeterminate />
          <button type="button" onClick={() => setDialogOpen(true)}>
            Open dialog
          </button>
          <Dialog {...typedDialog}>
            <Select
              options={options}
              value={dialogSelection}
              onChange={setDialogSelection}
              size="medium"
              label="Dialog option"
            />
            <Tooltip text="Inside dialog">
              <button type="button">Dialog hint</button>
            </Tooltip>
          </Dialog>
        </section>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <>
      <div id="outside-probe">Consumer-owned shell probe</div>
      <App />
    </>
  </StrictMode>,
);
