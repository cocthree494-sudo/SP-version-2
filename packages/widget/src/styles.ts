export const widgetStyles = `
:host { --sa-accent: #194f46; --sa-accent-soft: #e6f3ed; --sa-ink: #16312d; --sa-muted: #61736e; --sa-line: #dce7e2; position: fixed; right: 20px; bottom: 20px; z-index: 2147483000; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--sa-ink); color-scheme: light; }
:host([position="left"]) { right: auto; left: 20px; }
* { box-sizing: border-box; }
button, textarea { font: inherit; }
.launcher { display: grid; place-items: center; width: 56px; height: 56px; margin-left: auto; border: 0; border-radius: 18px; background: var(--sa-accent); color: white; cursor: pointer; box-shadow: 0 14px 34px rgba(20, 57, 50, .26); transition: transform .18s ease, box-shadow .18s ease; }
.launcher:hover { transform: translateY(-2px); box-shadow: 0 17px 38px rgba(20, 57, 50, .31); }
.launcher:focus-visible, button:focus-visible, textarea:focus-visible, a:focus-visible { outline: 3px solid color-mix(in srgb, var(--sa-accent), white 45%); outline-offset: 2px; }
.launcher svg { width: 24px; height: 24px; fill: none; stroke: currentColor; stroke-width: 1.8; }
.panel { position: absolute; right: 0; bottom: 68px; display: grid; grid-template-rows: auto minmax(260px, 1fr) auto; width: min(380px, calc(100vw - 28px)); height: min(610px, calc(100vh - 105px)); overflow: hidden; border: 1px solid var(--sa-line); border-radius: 20px; background: white; box-shadow: 0 24px 64px rgba(20, 49, 44, .22); transform-origin: bottom right; animation: sa-enter .18s ease-out; }
:host([position="left"]) .panel { right: auto; left: 0; transform-origin: bottom left; }
.header { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 70px; padding: 14px 15px 14px 18px; background: var(--sa-accent); color: white; }
.identity { min-width: 0; }
.identity strong, .identity span { display: block; }
.identity strong { font-size: 14px; letter-spacing: -.01em; }
.identity span { margin-top: 4px; overflow: hidden; color: rgba(255,255,255,.74); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.close { display: grid; place-items: center; flex: 0 0 auto; width: 34px; height: 34px; border: 0; border-radius: 10px; background: rgba(255,255,255,.12); color: white; cursor: pointer; font-size: 20px; }
.messages { display: flex; flex-direction: column; gap: 13px; overflow-y: auto; padding: 18px; background: #fbfdfc; overscroll-behavior: contain; }
.welcome { margin: auto 0; padding: 18px; text-align: center; }
.welcome-icon { display: grid; place-items: center; width: 43px; height: 43px; margin: 0 auto 14px; border-radius: 13px; background: var(--sa-accent-soft); color: var(--sa-accent); }
.welcome strong { display: block; font-size: 15px; }
.welcome p { margin: 7px auto 0; max-width: 260px; color: var(--sa-muted); font-size: 11px; line-height: 1.55; }
.bubble { width: fit-content; max-width: 86%; padding: 10px 12px; border-radius: 13px; font-size: 12px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.bubble-user { align-self: end; border-bottom-right-radius: 4px; background: var(--sa-accent); color: white; }
.bubble-agent { align-self: start; border: 1px solid var(--sa-line); border-bottom-left-radius: 4px; background: white; color: var(--sa-ink); }
.typing { display: flex; align-items: center; gap: 4px; min-width: 48px; min-height: 37px; }
.typing i { width: 5px; height: 5px; border-radius: 50%; background: #83a298; animation: sa-dot 1s infinite ease-in-out; }
.typing i:nth-child(2) { animation-delay: .14s; }.typing i:nth-child(3) { animation-delay: .28s; }
.citations { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.citations a, .citations span { max-width: 100%; overflow: hidden; padding: 4px 6px; border: 1px solid var(--sa-line); border-radius: 5px; color: var(--sa-accent); font-size: 9px; font-weight: 700; text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }
.error { margin: 0 18px 12px; padding: 9px 10px; border-radius: 8px; background: #fff0ed; color: #913f32; font-size: 10px; line-height: 1.45; }
.retry { margin-top: 6px; padding: 0; border: 0; background: transparent; color: inherit; cursor: pointer; font-weight: 800; text-decoration: underline; }
.composer { padding: 12px; border-top: 1px solid var(--sa-line); background: white; }
.composer-row { display: grid; grid-template-columns: minmax(0,1fr) auto; align-items: end; gap: 8px; }
.composer textarea { width: 100%; min-height: 44px; max-height: 110px; resize: none; padding: 10px 11px; border: 1px solid #cedbd5; border-radius: 10px; outline: 0; color: var(--sa-ink); font-size: 12px; line-height: 1.45; }
.send { display: grid; place-items: center; width: 42px; height: 42px; border: 0; border-radius: 11px; background: var(--sa-accent); color: white; cursor: pointer; }
.send:disabled, .composer textarea:disabled { cursor: not-allowed; opacity: .5; }
.send svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; }
.powered { display: block; margin-top: 7px; color: #87958f; font-size: 8px; text-align: center; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); clip-path: inset(50%); white-space: nowrap; }
@keyframes sa-enter { from { opacity: 0; transform: translateY(8px) scale(.98); } }
@keyframes sa-dot { 0%,70%,100% { opacity: .35; transform: translateY(0); } 35% { opacity: 1; transform: translateY(-2px); } }
@media (max-width: 520px) { :host { right: 12px; bottom: 12px; } :host([position="left"]) { left: 12px; } .panel { position: fixed; inset: 10px 10px 78px; width: auto; height: auto; border-radius: 17px; } .launcher { width: 54px; height: 54px; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; } }
`;
