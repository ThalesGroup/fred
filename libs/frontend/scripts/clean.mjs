import { fileURLToPath } from "node:url";
import { rm } from "node:fs/promises";
import path from "node:path";

const workspaceRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

await Promise.all([
  rm(path.join(workspaceRoot, "target"), { recursive: true, force: true }),
  rm(path.join(workspaceRoot, "design-tokens/dist"), {
    recursive: true,
    force: true,
  }),
  rm(path.join(workspaceRoot, "design-tokens/LICENSE"), { force: true }),
  rm(path.join(workspaceRoot, "design-tokens/licenses"), {
    recursive: true,
    force: true,
  }),
]);
