# Isolated embeddable widget

T-053 ships the support client as a Preact custom element named
`<support-agent>`. A small `loader.js` discovers configuration from its own data
attributes, creates the element when needed, and loads `widget.js` on the first
interaction or an idle timeout. The widget attaches an open Shadow DOM and
injects all styles inside it, preventing host-page CSS from changing the chat UI
and preventing widget selectors from leaking into the host.

The component keeps the short-lived anonymous session token only in memory. It
creates a session through the exact-origin checked public API and consumes answer
events incrementally from SSE. Text replacement, citations, completion, safe
terminal errors, retry, expired-session recovery on the next turn, and stream
cancellation on close/disconnect are handled without browser storage.

The launcher and panel expose keyboard focus states, labelled controls, an ARIA
dialog/live region, Enter-to-send with Shift+Enter for a newline, reduced-motion
support, and a near-full-screen mobile layout. Shadow-DOM variables accept only a
browser-validated color value. The publishable key remains a public identifier;
server-side allowed-origin checks are always authoritative.

## Bundle report

`npm run build --workspace @support-agent/widget` writes
`dist/bundle-report.json` after every production build. The T-053 baseline is:

| File | Raw | Gzip |
|---|---:|---:|
| `loader.js` | 1.87 KB | 0.99 KB |
| `widget.js` | 25.56 KB | 10.03 KB |
| Total | 27,433 bytes | 10,965 bytes |

The loader and widget are separate entry points, so host pages pay roughly one
kilobyte gzip before lazy loading the interactive client. Bundle growth should be
reviewed against this checked baseline during later production acceptance.
