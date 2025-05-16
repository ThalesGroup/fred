import React, { createContext, useContext, useState } from "react";
import { Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Button } from "@mui/material";

// Define the structure for the confirmation dialog
interface ConfirmationDialogOptions {
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel?: () => void;
}

// Create the ConfirmationDialogContext
const ConfirmationDialogContext = createContext<any>(null);

export const ConfirmationDialogProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [dialogOptions, setDialogOptions] = useState<ConfirmationDialogOptions | null>(null);

  // Function to show a confirmation dialog
  const showConfirmationDialog = (options: ConfirmationDialogOptions) => {
    setDialogOptions(options);
  };

  // Function to close the confirmation dialog
  const closeConfirmationDialog = () => {
    setDialogOptions(null);
  };

  return (
    <ConfirmationDialogContext.Provider value={{ showConfirmationDialog }}>
      {children}
      
      {dialogOptions && (
        <Dialog open={true} onClose={closeConfirmationDialog}>
          <DialogTitle>{dialogOptions.title}</DialogTitle>
          <DialogContent>
            <DialogContentText>{dialogOptions.message}</DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={closeConfirmationDialog} color="secondary">Cancel</Button>
            <Button 
              onClick={() => {
                dialogOptions.onConfirm();
                closeConfirmationDialog();
              }} 
              color="primary"
              autoFocus
            >
              Confirm
            </Button>
          </DialogActions>
        </Dialog>
      )}
    </ConfirmationDialogContext.Provider>
  );
};

export const useConfirmationDialog = () => {
  return useContext(ConfirmationDialogContext);
};