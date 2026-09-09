import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { Button, Icon, IconButton, Spinner, TextInput } from "@fred/ui";
import type {
  ButtonProps,
  ButtonSize,
  ButtonVariant,
  ColorTheme,
  IconButtonProps,
  IconButtonVariant,
  IconProps,
  MaterialIconType,
  SpinnerProps,
  TextInputProps,
} from "@fred/ui";
import "@fred/design-tokens/tokens.css";
import "@fred/ui/styles.css";
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

function App() {
  const [clicks, setClicks] = useState(0);
  const [name, setName] = useState("Fred");
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
