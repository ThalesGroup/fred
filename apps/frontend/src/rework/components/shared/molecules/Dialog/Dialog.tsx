// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

import { useTranslation } from "react-i18next";
import { DialogPrimitive, type DialogProps } from "./DialogPrimitive";

/** Application wrapper preserving FRED's translated default; the package exports DialogPrimitive. */
export function Dialog(props: DialogProps) {
  const { t } = useTranslation();
  return <DialogPrimitive {...props} cancelLabel={props.cancelLabel ?? t("common.cancel")} />;
}

export type { DialogProps } from "./DialogPrimitive";
