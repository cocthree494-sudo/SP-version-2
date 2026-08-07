const script = document.currentScript as HTMLScriptElement | null;

if (script) {
  const existing = document.querySelector("support-agent");
  const element = existing ?? document.createElement("support-agent");
  const attributes = ["api-base", "publishable-key", "welcome", "accent", "title", "position"];
  for (const attribute of attributes) {
    const value = script.dataset[attribute.replace(/-([a-z])/g, (_, letter: string) => letter.toUpperCase())];
    if (value && !element.hasAttribute(attribute)) element.setAttribute(attribute, value);
  }
  if (!existing) document.body.append(element);

  const widgetSource = script.dataset.widgetSrc || new URL("./widget.js", script.src).href;
  let loading: Promise<void> | null = null;
  const load = () => {
    loading ??= new Promise<void>((resolve, reject) => {
      if (customElements.get("support-agent")) {
        resolve();
        return;
      }
      const widgetScript = document.createElement("script");
      widgetScript.type = "module";
      widgetScript.src = widgetSource;
      if (script.nonce) widgetScript.nonce = script.nonce;
      widgetScript.addEventListener("load", () => resolve(), { once: true });
      widgetScript.addEventListener(
        "error",
        () => reject(new Error("Unable to load the support widget")),
        { once: true },
      );
      document.head.append(widgetScript);
    });
    return loading;
  };
  for (const event of ["pointerdown", "keydown", "touchstart"] as const) {
    window.addEventListener(event, () => void load(), { once: true, passive: true });
  }
  const idle = Reflect.get(window, "requestIdleCallback") as
    | ((callback: () => void, options: { timeout: number }) => number)
    | undefined;
  if (typeof idle === "function") {
    idle(() => void load(), { timeout: 1800 });
  } else {
    globalThis.setTimeout(() => void load(), 1200);
  }
}
