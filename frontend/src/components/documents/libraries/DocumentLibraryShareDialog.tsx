import { Button, Dialog, DialogActions, DialogContent, DialogTitle } from "@mui/material";
import { useTranslation } from "react-i18next";

interface DocumentLibraryShareDialogProps {
  open: boolean;
  folderName?: string;
  onClose: () => void;
}

export function DocumentLibraryShareDialog({ open, folderName, onClose }: DocumentLibraryShareDialogProps) {
  const { t } = useTranslation();
  const title = folderName
    ? t("documentLibraryTree.shareFolderWithName", { name: folderName })
    : t("documentLibraryTree.shareFolder");

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>{t("documentLibraryTree.shareModalPlaceholder")}</DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("common.close")}</Button>
      </DialogActions>
    </Dialog>
  );
}
