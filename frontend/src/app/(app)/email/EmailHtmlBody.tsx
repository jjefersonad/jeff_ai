/**
 * Isolated HTML body for the inbox detail view (REQ-014 / REQ-016).
 *
 * Renders sanitized `body_html` inside a sandboxed `srcDoc` iframe so
 * application CSS (`prose`, dark theme) cannot restyle the message.
 * The HTML is already sanitized at IMAP ingest (`nh3`); this component
 * does not re-sanitize.
 */

interface EmailHtmlBodyProps {
  html: string;
}

const SANDBOX = "allow-popups allow-popups-to-escape-sandbox";

const WRAPPER_STYLE = [
  "html,body{margin:0;background:#fff;color:#111;}",
  "img{max-width:100%;height:auto;}",
  "body{overflow:auto;}",
].join("");

function wrapHtmlDocument(html: string): string {
  return (
    `<!DOCTYPE html><html><head>` +
    `<meta charset="utf-8">` +
    `<base target="_blank" rel="noopener noreferrer">` +
    `<style>${WRAPPER_STYLE}</style>` +
    `</head><body>${html}</body></html>`
  );
}

export function EmailHtmlBody({ html }: EmailHtmlBodyProps) {
  return (
    <iframe
      title="Corpo do e-mail"
      srcDoc={wrapHtmlDocument(html)}
      sandbox={SANDBOX}
      referrerPolicy="no-referrer"
      className="h-full w-full border-0 bg-white"
    />
  );
}
