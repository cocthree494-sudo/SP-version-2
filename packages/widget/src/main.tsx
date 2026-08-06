import "./widget";

const root = document.querySelector<HTMLDivElement>("#app");
if (root) {
  const widget = document.createElement("support-agent");
  widget.setAttribute("api-base", "http://127.0.0.1:8000");
  widget.setAttribute("publishable-key", "pk_preview");
  widget.setAttribute("welcome", "Welcome to the widget preview");
  root.append(widget);
}
