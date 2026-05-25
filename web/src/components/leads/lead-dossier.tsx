/**
 * Mini-Markdown-Renderer für 1-Seiten-Dossier.
 * Wir nutzen kein heavyweight-Lib (react-markdown bringt 200KB) — eigene
 * tighte Implementierung für die wenigen Konstrukte die wir nutzen.
 */

export function LeadDossier({ markdown }: { markdown: string }) {
  const blocks = markdown.split(/\n\n+/);

  return (
    <div className="prose-sm max-w-none text-sm leading-relaxed space-y-3">
      {blocks.map((b, i) => {
        const trimmed = b.trim();
        if (!trimmed) return null;

        // Headers
        if (trimmed.startsWith("# ")) {
          return (
            <h1 key={i} className="text-base font-semibold tracking-tight">
              {trimmed.slice(2)}
            </h1>
          );
        }
        if (trimmed.startsWith("## ")) {
          return (
            <h2
              key={i}
              className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] mt-4 mb-1"
            >
              {trimmed.slice(3)}
            </h2>
          );
        }

        // Lists
        if (/^[-*]\s/.test(trimmed)) {
          const items = trimmed
            .split("\n")
            .filter((l) => /^[-*]\s/.test(l))
            .map((l) => l.replace(/^[-*]\s/, ""));
          return (
            <ul key={i} className="list-disc pl-5 space-y-1 text-xs">
              {items.map((it, j) => (
                <li key={j} dangerouslySetInnerHTML={{ __html: renderInline(it) }} />
              ))}
            </ul>
          );
        }

        // Numbered lists
        if (/^\d+\./.test(trimmed)) {
          const items = trimmed.split("\n").filter((l) => /^\d+\./.test(l));
          return (
            <ol key={i} className="list-decimal pl-5 space-y-1 text-xs">
              {items.map((l, j) => (
                <li
                  key={j}
                  dangerouslySetInnerHTML={{
                    __html: renderInline(l.replace(/^\d+\.\s*/, "")),
                  }}
                />
              ))}
            </ol>
          );
        }

        return (
          <p
            key={i}
            className="text-xs"
            dangerouslySetInnerHTML={{ __html: renderInline(trimmed) }}
          />
        );
      })}
    </div>
  );
}

// Phase 8.2-Audit-P4: XSS-Schutz — escape HTML-Special-Chars BEVOR
// Markdown-Replacements. Sonst können HR-Bekanntmachungs-Texte mit
// <script>/<img onerror=...>/etc. ins DOM injected werden.
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInline(text: string): string {
  // STEP 1: Escape HTML-Special-Chars (XSS-Schutz)
  let safe = escapeHtml(text);
  // STEP 2: Markdown-Replacements (sichere Tags die WIR generieren)
  // bold: **text**
  safe = safe.replace(
    /\*\*([^*]+)\*\*/g,
    '<strong class="font-medium text-[var(--foreground)]">$1</strong>',
  );
  // inline-code: `text`
  safe = safe.replace(
    /`([^`]+)`/g,
    '<code class="font-mono text-[11px] px-1 rounded bg-[var(--muted)]">$1</code>',
  );
  return safe;
}
