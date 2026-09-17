import { createRoot } from "react-dom/client";
import { ApplicationContext } from "./application-download-mocks.tsx";
import TeamApplicationHostPage from "../../../../apps/frontend/src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.tsx";

const root = document.getElementById("root");
if (!root) throw new Error("production-host fixture root is missing");

createRoot(root).render(
  <ApplicationContext.Provider value={{ darkMode: false }}>
    <TeamApplicationHostPage />
  </ApplicationContext.Provider>,
);
