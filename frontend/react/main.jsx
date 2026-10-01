import React from "react";
import { createRoot } from "react-dom/client";
import {
  AccountManagementWidget,
  AdminUsersWidget,
  AuthCallbackWidget,
  BackendStatusWidget,
  CaseInsightsWidget,
  ChatbotWidget,
  DocumentLibraryWidget,
  FileAnalysisWidget,
  LegalAssistantWidget,
} from "./LexoraApp.jsx";
import { ContractGenerationPage } from "./ContractGeneration.jsx";

const widgets = {
  "account-management": AccountManagementWidget,
  "admin-users": AdminUsersWidget,
  "backend-status": BackendStatusWidget,
  "case-insights": CaseInsightsWidget,
  chatbot: ChatbotWidget,
  "document-library": DocumentLibraryWidget,
  "file-analysis": FileAnalysisWidget,
  "legal-assistant": LegalAssistantWidget,
  "contract-generation": ContractGenerationPage,
};

document.querySelectorAll("[data-react-widget]").forEach((element) => {
  const Widget = widgets[element.dataset.reactWidget];

  if (!Widget || element.dataset.reactMounted === "true") return;

  element.dataset.reactMounted = "true";

 createRoot(element).render(
  <Widget {...element.dataset} />,
);
});

const callbackAction = window.location.pathname.match(/\/(reset-password|confirm-email|confirm-email-change)\/?$/)?.[1];
if (callbackAction) {
  const callbackRoot = document.createElement("div");
  callbackRoot.id = "auth-callback-root";
  document.body.appendChild(callbackRoot);
  createRoot(callbackRoot).render(<AuthCallbackWidget action={callbackAction} />);
}
