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

export const UI_COMPONENT_SOURCE_PATHS = [
  "apps/frontend/src/rework/components/shared/utils/Type.ts",
  "apps/frontend/src/rework/components/shared/atoms/Icon/Icon.tsx",
  "apps/frontend/src/rework/components/shared/atoms/Icon/Icon.module.scss",
  "apps/frontend/src/rework/components/shared/atoms/Spinner/Spinner.tsx",
  "apps/frontend/src/rework/components/shared/atoms/Spinner/Spinner.module.css",
  "apps/frontend/src/rework/components/shared/atoms/Button/Button.tsx",
  "apps/frontend/src/rework/components/shared/atoms/Button/Button.module.scss",
  "apps/frontend/src/rework/components/shared/atoms/IconButton/IconButton.tsx",
  "apps/frontend/src/rework/components/shared/atoms/IconButton/IconButton.module.scss",
  "apps/frontend/src/rework/components/shared/atoms/TextInput/TextInput.tsx",
  "apps/frontend/src/rework/components/shared/atoms/TextInput/TextInput.module.scss",
];

export const UI_STYLE_SUPPORT_PATHS = [
  "apps/frontend/src/index.scss",
  FONT_STYLESHEET_PATH,
];

export const UI_REACT_BASELINE_PATHS = [
  "apps/frontend/package.json",
  "apps/frontend/package-lock.json",
];

export const IFRAME_SDK_CANONICAL_SOURCE_PATH =
  "apps/frontend/src/rework/features/applications/applicationProtocol.ts";

export const IFRAME_SDK_SOURCE_PATHS = [
  IFRAME_SDK_CANONICAL_SOURCE_PATH,
  "libs/frontend/iframe-sdk/src/index.ts",
];

export const IFRAME_HOST_COMPATIBILITY_PATHS = [
  IFRAME_SDK_CANONICAL_SOURCE_PATH,
  "apps/frontend/src/rework/features/applications/applicationProtocol.test.ts",
  "apps/frontend/src/rework/features/applications/applicationHost.ts",
  "apps/frontend/src/rework/features/applications/applicationHost.test.ts",
  "apps/frontend/src/rework/features/applications/applicationPath.ts",
  "apps/frontend/src/rework/features/applications/applicationPath.test.ts",
  "apps/frontend/src/rework/features/applications/applicationRequest.ts",
  "apps/frontend/src/rework/features/applications/applicationRequest.test.ts",
  "apps/frontend/src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.tsx",
  "apps/frontend/src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.test.tsx",
  "apps/frontend/src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.sdk-integration.test.tsx",
];

export const UI_FONT_SOURCE = {
  sourcePath: "apps/frontend/src/assets/fonts/material-symbols-outlined.woff2",
  packedName: "MaterialSymbolsOutlined.woff2",
  sha256: "98817d23c038afb643c659819b194fa4146880c54f2f14d12c1710a5c41760d7",
  size: 3864540,
  upstream: {
    repository: "https://github.com/google/material-design-icons",
    commit: "caeba1e66925218b1fd1464171f93e2656f9a0b9",
    commitDate: "2026-02-20T03:12:50Z",
    path: "variablefont/MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].woff2",
    blobSha: "d1c6a887e4663ac3e9c5feee3d13863f1bb58140",
  },
};

export const UI_LICENSE_INPUT_PATH =
  "libs/frontend/ui/license-inputs/Material-Symbols-Apache-2.0.txt";

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
  ...UI_COMPONENT_SOURCE_PATHS,
  ...UI_STYLE_SUPPORT_PATHS,
  ...FONT_SOURCES.map(({ sourcePath }) => sourcePath),
  UI_FONT_SOURCE.sourcePath,
  ...UI_REACT_BASELINE_PATHS,
  ...IFRAME_HOST_COMPATIBILITY_PATHS,
  ROOT_LICENSE_PATH,
  ...VALIDATION_ORCHESTRATION_PATHS,
];

export const CI_INPUT_PATTERNS = [
  PACKAGE_WORKSPACE_PATTERN,
  ...new Set(CI_EXACT_INPUTS),
];
