"use client";

import { useEffect, useState } from "react";
import { Phone, Mail, Link as LinkedinIcon, Globe, Smartphone, Copy, Check } from "lucide-react";

import type { ContactChannel, ContactChannelKind } from "@/lib/db/types";

type Props = {
  channels: ContactChannel[];
  // legacy single fields — fallback wenn channels-Array leer
  fallbackPhone: string | null;
  fallbackPhoneSource: string | null;
  fallbackEmail: string | null;
};

const ICONS: Record<ContactChannelKind, React.ComponentType<{ className?: string }>> = {
  phone: Phone,
  mobile: Smartphone,
  email: Mail,
  linkedin: LinkedinIcon,
  xing: LinkedinIcon,
  website: Globe,
};

const KIND_LABEL: Record<ContactChannelKind, string> = {
  phone: "Telefon",
  mobile: "Mobil",
  email: "E-Mail",
  linkedin: "LinkedIn",
  xing: "Xing",
  website: "Website",
};

function buildHref(c: ContactChannel): string | null {
  if (c.channel === "phone" || c.channel === "mobile") {
    return `tel:${c.value.replace(/[^+\d]/g, "")}`;
  }
  if (c.channel === "email") return `mailto:${c.value}`;
  if (c.channel === "linkedin" || c.channel === "xing" || c.channel === "website") {
    return c.value.startsWith("http") ? c.value : `https://${c.value}`;
  }
  return null;
}

export function LeadContactChannels({
  channels,
  fallbackPhone,
  fallbackPhoneSource,
  fallbackEmail,
}: Props) {
  // Build effective list: prefer array, else synthesize from legacy
  const list: ContactChannel[] =
    channels && channels.length > 0
      ? channels
      : [
          ...(fallbackPhone
            ? [
                {
                  channel: "phone" as const,
                  value: fallbackPhone,
                  source: fallbackPhoneSource ?? "legacy",
                  confidence: 0.7,
                  notes: null,
                },
              ]
            : []),
          ...(fallbackEmail
            ? [
                {
                  channel: "email" as const,
                  value: fallbackEmail,
                  source: "legacy",
                  confidence: 0.6,
                  notes: null,
                },
              ]
            : []),
        ];

  const top = list.slice(0, 3);
  const more = list.slice(3);
  const [showAll, setShowAll] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState<number>(0);

  // Keyboard shortcuts 1/2/3 → open primary channel
  useEffect(() => {
    if (top.length === 0) return;
    const handler = (e: KeyboardEvent) => {
      // Skip if user is typing in an input
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      )
        return;
      if (e.key === "1" && top[0]) openChannel(top[0]);
      else if (e.key === "2" && top[1]) openChannel(top[1]);
      else if (e.key === "3" && top[2]) openChannel(top[2]);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [top]);

  function openChannel(c: ContactChannel) {
    const href = buildHref(c);
    if (href) {
      if (c.channel === "phone" || c.channel === "mobile" || c.channel === "email") {
        window.location.href = href;
      } else {
        window.open(href, "_blank", "noopener,noreferrer");
      }
    }
  }

  async function copyValue(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(value);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      /* clipboard kann blockiert sein */
    }
  }

  if (list.length === 0) {
    return (
      <div className="text-xs text-[var(--muted-foreground)]">
        Keine Kontaktdaten gefunden — Closer-Recherche nötig.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)] mb-1 flex items-center justify-between">
        <span>Kontakt-Kanäle</span>
        <span className="text-[9px] text-[var(--muted-foreground)] font-mono">
          Tasten 1·2·3
        </span>
      </div>
      <ul className="space-y-1.5">
        {top.map((c, i) => {
          const Icon = ICONS[c.channel];
          const href = buildHref(c);
          return (
            <li
              key={`${c.channel}:${c.value}`}
              className={`group flex items-center gap-2 p-1.5 -mx-1.5 rounded transition-colors ${
                activeIndex === i ? "bg-[var(--accent)]" : "hover:bg-[var(--accent)]/50"
              }`}
              onMouseEnter={() => setActiveIndex(i)}
            >
              <span className="size-5 flex items-center justify-center text-[10px] font-mono text-[var(--muted-foreground)] tabular-nums">
                {i + 1}
              </span>
              <Icon className="size-3.5 text-[var(--muted-foreground)] shrink-0" />
              <div className="min-w-0 flex-1">
                {href ? (
                  <a
                    href={href}
                    target={
                      c.channel === "linkedin" || c.channel === "xing" || c.channel === "website"
                        ? "_blank"
                        : undefined
                    }
                    rel="noopener noreferrer"
                    className="text-sm font-medium hover:text-[var(--primary)] transition-colors tabular-nums truncate block"
                  >
                    {c.value}
                  </a>
                ) : (
                  <span className="text-sm">{c.value}</span>
                )}
                <div className="text-[10px] text-[var(--muted-foreground)] flex items-center gap-1.5 truncate">
                  <span>{KIND_LABEL[c.channel]}</span>
                  <span>·</span>
                  <span
                    className="font-mono"
                    title={`Confidence ${Math.round(c.confidence * 100)}%`}
                  >
                    {Math.round(c.confidence * 100)}%
                  </span>
                  {c.notes && (
                    <>
                      <span>·</span>
                      <span className="italic">{c.notes}</span>
                    </>
                  )}
                </div>
              </div>
              <button
                onClick={() => copyValue(c.value)}
                className="opacity-0 group-hover:opacity-100 size-6 flex items-center justify-center rounded hover:bg-[var(--background)] transition-all"
                title="Kopieren"
              >
                {copied === c.value ? (
                  <Check className="size-3 text-[oklch(0.71_0.18_152)]" />
                ) : (
                  <Copy className="size-3 text-[var(--muted-foreground)]" />
                )}
              </button>
            </li>
          );
        })}
      </ul>

      {more.length > 0 && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="text-[10px] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors mt-2"
        >
          {showAll ? "weniger anzeigen" : `+${more.length} weitere Kanäle`}
        </button>
      )}

      {showAll && (
        <ul className="space-y-1 pt-2 border-t border-[var(--border)] mt-2">
          {more.map((c) => {
            const Icon = ICONS[c.channel];
            const href = buildHref(c);
            return (
              <li key={`${c.channel}:${c.value}`} className="flex items-center gap-2 text-xs">
                <Icon className="size-3 text-[var(--muted-foreground)] shrink-0" />
                {href ? (
                  <a
                    href={href}
                    target={c.channel === "email" ? undefined : "_blank"}
                    rel="noopener noreferrer"
                    className="text-[var(--muted-foreground)] hover:text-[var(--foreground)] truncate"
                  >
                    {c.value}
                  </a>
                ) : (
                  <span className="text-[var(--muted-foreground)] truncate">{c.value}</span>
                )}
                <span className="text-[9px] text-[var(--muted-foreground)] font-mono ml-auto shrink-0">
                  {Math.round(c.confidence * 100)}%
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
