export const TOKEN_SOURCE_PATHS = [
  "apps/frontend/src/styles/color-ramps.css",
  "apps/frontend/src/styles/colors-semantic-light.css",
  "apps/frontend/src/styles/colors-semantic-dark.css",
  "apps/frontend/src/styles/colors-state-semantic.css",
  "apps/frontend/src/styles/shadow-light.css",
  "apps/frontend/src/styles/shadow-dark.css",
  "apps/frontend/src/styles/spacings.css",
  "apps/frontend/src/styles/radius.css",
  "apps/frontend/src/styles/motion.css",
  "apps/frontend/src/styles/gradients.css",
  "apps/frontend/src/styles/typography.css",
];

export const FONT_STYLESHEET_PATH = "apps/frontend/src/styles/index.css";

export const FONT_SOURCES = [
  {
    style: "normal",
    sourcePath: "apps/frontend/src/assets/fonts/Geist.woff2",
    packedName: "Geist.woff2",
    sha256: "76cfe85ecc60501d14d0309e96875e736be40c80a8e8cd0746f3469bd44fc724",
  },
  {
    style: "italic",
    sourcePath: "apps/frontend/src/assets/fonts/Geist-Italic.woff2",
    packedName: "Geist-Italic.woff2",
    sha256: "bc44b49662a093f12418c30fc526ee7caa07a3fb438f1585f43ac12ef0566516",
  },
];

export const ROOT_LICENSE_PATH = "LICENSE";
export const LICENSE_FILES = [
  {
    packedPath: "LICENSE",
    sha256: "c4f0580f5e58f572f41c1985ac9920c227c166f09d25cba1a01ace86409c6e5c",
  },
  {
    packedPath: "licenses/Geist-OFL-1.1.txt",
    sha256: "942560b236adfa83745b2c64e5fc09ebaf91cb331751b1157eb92187e5d6e930",
  },
];
export const PACKAGE_WORKSPACE_PATTERN = "libs/frontend/**";
export const WORKFLOW_PATH = ".github/workflows/Check-pending-requests.yml";

export const VALIDATION_ORCHESTRATION_PATHS = ["Makefile", WORKFLOW_PATH];

export const CI_EXACT_INPUTS = [
  ...TOKEN_SOURCE_PATHS,
  FONT_STYLESHEET_PATH,
  ...FONT_SOURCES.map(({ sourcePath }) => sourcePath),
  ROOT_LICENSE_PATH,
  ...VALIDATION_ORCHESTRATION_PATHS,
];

export const CI_INPUT_PATTERNS = [
  PACKAGE_WORKSPACE_PATTERN,
  ...CI_EXACT_INPUTS,
];
