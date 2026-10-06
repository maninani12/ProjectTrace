import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./public/public.css";
const target = document.getElementById("root")!;
const view = (
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
if (
  target.hasChildNodes() &&
  target.dataset.prerenderPath ===
    (window.location.pathname.replace(/\/$/, "") || "/")
)
  ReactDOM.hydrateRoot(target, view);
else {
  target.replaceChildren();
  ReactDOM.createRoot(target).render(view);
}
