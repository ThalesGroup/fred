import { Button, IconButton } from "@fred/ui";

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

export { badButton, badIconButton };
