// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { HashRouter, Link, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { applyResolvedTheme } from "../../app/uiThemes";
import { ApplicationContextProvider } from "../../app/ApplicationContextProvider";
import { knowledgeFlowApi } from "../../slices/legacyKnowledgeFlow/knowledgeFlowApi";
import { legacyControlPlaneApi } from "../../slices/legacyControlPlane/legacyControlPlaneApi";
import { controlPlaneApi } from "../../slices/controlPlane/controlPlaneApi";
import { taskSlice } from "../../rework/features/tasks/taskSlice";
import { weaverFeatures } from "../../rework/features/weaver/catalog";
import { ConfirmationDialogProvider } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { ToastProvider } from "@shared/molecules/Toast/ToastProvider";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import CorpusAuditPage from "@components/pages/admin/CorpusAuditPage/CorpusAuditPage";
import TasksPage from "@components/pages/admin/TasksPage/TasksPage";
import MigrationPage from "@components/pages/admin/MigrationPage/MigrationPage";
import SelfTestPage from "@components/pages/admin/SelfTestPage/SelfTestPage";
import TeamKnowledgeBasesPage from "@components/pages/TeamKnowledgeBasesPage/TeamKnowledgeBasesPage";
import KnowledgeBaseDocumentsPage from "@components/pages/TeamKnowledgeBasesPage/KnowledgeBaseDocumentsPage";
import DocumentWorkspace from "@components/pages/TeamResourcesPage/DocumentWorkspace/DocumentWorkspace";
import { RichInputField } from "@shared/molecules/RichInputField/RichInputField";
import "../../i18n";
import "../../styles.css";
import "../../styles/utils.css";
import "../../styles/index.css";
import "../../index.scss";
import "@fontsource/inter/400.css";
import "@fontsource/nunito/400.css";
import styles from "./PreviewApp.module.css";

const store = configureStore({
  reducer: {
    swiftPreview: () => true,
    tasks: taskSlice.reducer,
    [knowledgeFlowApi.reducerPath]: knowledgeFlowApi.reducer,
    [legacyControlPlaneApi.reducerPath]: legacyControlPlaneApi.reducer,
    [controlPlaneApi.reducerPath]: controlPlaneApi.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(
      knowledgeFlowApi.middleware,
      legacyControlPlaneApi.middleware,
      controlPlaneApi.middleware,
    ),
});

function DictationPreview() {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const { t } = useTranslation();
  return (
    <section>
      <p>{t("rework.weaver.dictationHint")}</p>
      <RichInputField
        value={value}
        onChange={setValue}
        onSend={() => setValue("")}
        enableVoiceInput
        onTranscribeAudio={async () => t("rework.weaver.dictatedText")}
        onVoiceInputError={setError}
      />
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

function PreviewApp() {
  const { t } = useTranslation();
  return (
    <div className={styles.shell}>
      <header>
        <ServiceNotice
          color="info"
          title={t("rework.weaver.previewTitle")}
          description={t("rework.weaver.previewDisclaimer")}
        />
        <nav className={styles.navigation} aria-label={t("rework.weaver.title")}>
          {weaverFeatures.map((feature) => (
            <Link key={feature.id} to={feature.preview}>
              {t(`rework.weaver.features.${feature.id}.title`)}
            </Link>
          ))}
        </nav>
      </header>
      <main className={styles.content}>
        <Routes>
          <Route path="/admin/corpus-audit" element={<CorpusAuditPage />} />
          <Route path="/admin/tasks" element={<TasksPage />} />
          <Route path="/admin/migration" element={<MigrationPage />} />
          <Route path="/admin/self-test" element={<SelfTestPage />} />
          <Route path="/team/:teamId/knowledge-bases" element={<TeamKnowledgeBasesPage />} />
          <Route path="/team/:teamId/knowledge-bases/:instanceId" element={<KnowledgeBaseDocumentsPage />} />
          <Route path="/documents" element={<DocumentWorkspace teamId="preview-team" isPersonalTeam={false} />} />
          <Route path="/dictation" element={<DictationPreview />} />
          <Route path="*" element={<p>{t("rework.weaver.choose")}</p>} />
        </Routes>
      </main>
    </div>
  );
}

applyResolvedTheme(null);
createRoot(document.getElementById("root")!).render(
  <Provider store={store}>
    <ApplicationContextProvider>
      <HashRouter>
        <ConfirmationDialogProvider>
          <ToastProvider>
            <PreviewApp />
          </ToastProvider>
        </ConfirmationDialogProvider>
      </HashRouter>
    </ApplicationContextProvider>
  </Provider>,
);
