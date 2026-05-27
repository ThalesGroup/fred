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

import { ConfirmationDialog } from "../rework/components/shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { createContext, PropsWithChildren, useContext, useState } from "react";
import { useTranslation } from "react-i18next";

// Define the structure for the confirmation dialog
interface ConfirmationDialogOptions {
  title: string;
  message?: string;
  confirmButtonLabel?: string;
  cancelButtonLabel?: string;
  criticalAction?: boolean;
  onConfirm: () => void;
  onCancel?: () => void;
}

// Define the context type
interface ConfirmationDialogContextType {
  showConfirmationDialog: (options: ConfirmationDialogOptions) => void;
}

// Create the ConfirmationDialogContext
const ConfirmationDialogContext = createContext<ConfirmationDialogContextType | null>(null);

export const ConfirmationDialogProvider = ({ children }: PropsWithChildren) => {
  const { t } = useTranslation();
  const [dialogOptions, setDialogOptions] = useState<ConfirmationDialogOptions | null>(null);

  // Function to show a confirmation dialog
  const showConfirmationDialog = (options: ConfirmationDialogOptions) => {
    setDialogOptions(options);
  };

  // Function to close the confirmation dialog
  const closeConfirmationDialog = () => {
    setDialogOptions(null);
  };

  const { criticalAction = false } = dialogOptions || {};

  return (
    <ConfirmationDialogContext.Provider value={{ showConfirmationDialog }}>
      {children}

      <ConfirmationDialog
        open={!!dialogOptions}
        title={dialogOptions?.title ?? ""}
        message={dialogOptions?.message}
        confirmLabel={dialogOptions?.confirmButtonLabel || t("confirmationDialog.defaultConfirmButtonLabel")}
        cancelLabel={dialogOptions?.cancelButtonLabel || t("confirmationDialog.defaultCancelButtonLabel")}
        criticalAction={criticalAction}
        onConfirm={() => {
          dialogOptions?.onConfirm();
          closeConfirmationDialog();
        }}
        onCancel={() => {
          dialogOptions?.onCancel?.();
          closeConfirmationDialog();
        }}
      />
    </ConfirmationDialogContext.Provider>
  );
};

export const useConfirmationDialog = (): ConfirmationDialogContextType => {
  const context = useContext(ConfirmationDialogContext);
  if (!context) {
    throw new Error("useConfirmationDialog must be used within a ConfirmationDialogProvider");
  }
  return context;
};
