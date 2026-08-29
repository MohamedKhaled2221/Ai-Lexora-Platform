import React from "react";
import { createRoot } from "react-dom/client";
import {
  BackendStatusWidget,
  CaseInsightsWidget,
  LegalAssistantWidget,
} from "./LexoraApp.jsx";

const widgets = {
  "backend-status": BackendStatusWidget,
  "case-insights": CaseInsightsWidget,
  "legal-assistant": LegalAssistantWidget,
};

document.querySelectorAll("[data-react-widget]").forEach((element) => {
  const Widget = widgets[element.dataset.reactWidget];

  if (!Widget || element.dataset.reactMounted === "true") return;

  element.dataset.reactMounted = "true";

  createRoot(element).render(
    <React.StrictMode>
      <Widget {...element.dataset} />
    </React.StrictMode>,
  );
});
