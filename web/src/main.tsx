import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ErrorBoundary } from "./ErrorBoundary";
import "./styles/tokens.css";
import "./styles/app.css";

const rootElement = document.getElementById("root");
if (rootElement === null) {
  throw new Error("#root element is missing from index.html");
}

createRoot(rootElement).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
