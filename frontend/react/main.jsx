import React from "react";
import { createRoot } from "react-dom/client";
import LexoraApp from "./LexoraApp.jsx";

const rootElement = document.createElement("div");

rootElement.setAttribute("data-react-root", "");
document.body.replaceChildren(rootElement);

createRoot(rootElement).render(
  <React.StrictMode>
    <LexoraApp />
  </React.StrictMode>,
);
