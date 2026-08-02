import { API_VERSION } from "@support-agent/api-client";
import { render } from "preact";

import "./style.css";

function WidgetScaffold() {
  return (
    <main>
      <strong>Support widget scaffold</strong>
      <span>API contract: {API_VERSION}</span>
    </main>
  );
}

const root = document.querySelector<HTMLDivElement>("#app");

if (root) {
  render(<WidgetScaffold />, root);
}
