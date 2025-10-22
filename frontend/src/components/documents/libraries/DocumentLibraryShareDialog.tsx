import PersonAddAlt1OutlinedIcon from "@mui/icons-material/PersonAddAlt1Outlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import { Dialog, DialogContent, DialogTitle, Tab, Typography } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { TagWithItemsId } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { RoundTabs } from "../../RoundTabs";
import { DocumentLibraryShareAddTab } from "./DocumentLibraryShareAddTab";
import { DocumentLibraryShareCurrentAccessTab } from "./DocumentLibraryShareCurrentAccessTab";

interface DocumentLibraryShareDialogProps {
  tag?: TagWithItemsId;
  open: boolean;
  onClose: () => void;
}

type ShareTab = "add" | "current";

export function DocumentLibraryShareDialog({ tag, open, onClose }: DocumentLibraryShareDialogProps) {
  const { t } = useTranslation();

  const [activeTab, setActiveTab] = React.useState<ShareTab>("add");
  const [refreshKey, setRefreshKey] = React.useState(0);

  React.useEffect(() => {
    if (!open) {
      setActiveTab("add");
    }
  }, [open]);

  const handleShared = React.useCallback(() => {
    setRefreshKey((prev) => prev + 1);
    setActiveTab("current");
  }, []);

  if (!tag) return null;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        {t("documentLibraryTree.shareFolderWithName", { name: tag.name })}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {t("documentLibraryShareDialog.subtitle", {
            defaultValue: "Add users or groups and manage access permissions for this library.",
          })}
        </Typography>
      </DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
        <RoundTabs value={activeTab} onChange={(_, value) => setActiveTab(value as ShareTab)}>
          <Tab
            icon={<PersonAddAlt1OutlinedIcon fontSize="small" />}
            iconPosition="start"
            value="add"
            label={t("documentLibraryShareDialog.addAccessTab", { defaultValue: "Add access" })}
          />
          <Tab
            icon={<ShieldOutlinedIcon fontSize="small" />}
            iconPosition="start"
            value="current"
            label={t("documentLibraryShareDialog.currentAccessTab", { defaultValue: "Current access" })}
          />
        </RoundTabs>

        {activeTab === "add" ? (
          <DocumentLibraryShareAddTab key={`${tag.id}-${refreshKey}`} tag={tag} onShared={handleShared} />
        ) : (
          <DocumentLibraryShareCurrentAccessTab tag={tag} open={open} refreshKey={refreshKey} />
        )}
      </DialogContent>
    </Dialog>
  );
}
