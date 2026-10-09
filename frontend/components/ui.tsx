"use client";

import { useState } from "react";
import type { ReactNode } from "react";

const STATUS_CLASS: Record<string, string> = {
  QUALIFIED: "qualified",
  APPROVED: "approved",
  COMPLETED: "completed",
  AWAITING_APPROVAL: "awaiting-approval",
  RUNNING: "running",
  RESEARCHING: "researching",
  DISCOVERY: "discovery",
  QUEUED: "queued",
  MAYBE: "maybe",
  REJECTED: "rejected",
  FAILED: "failed",
  GO: "qualified",
  NO_GO: "failed",
};

export function humanize(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function StatusBadge({ status }: { status: string }) {
  const tone = STATUS_CLASS[status] ?? "";

  return (
    <span className={`status ${tone}`.trim()} data-status={status}>
      {humanize(status)}
    </span>
  );
}

export function DecisionBadge({ decision }: { decision: string }) {
  const tone = STATUS_CLASS[decision] ?? "";

  return (
    <span className={`status ${tone}`.trim()} data-decision={decision}>
      {humanize(decision)}
    </span>
  );
}

/**
 * Qualification confidence as stored by the agent (0–1, or 0–100 when a
 * breakdown value is passed in). Rendered as a percentage with a tone dot.
 */
export function ConfidenceValue({
  value,
}: {
  value: number | null | undefined;
}) {
  if (value === null || value === undefined) {
    return <span className="faint">—</span>;
  }

  const percent = value <= 1 ? value * 100 : value;
  const tone = percent >= 75 ? "high" : percent >= 45 ? "medium" : "low";

  return (
    <span className={`confidence ${tone}`} title={`${percent.toFixed(0)}% confidence`}>
      <i />
      {Math.round(percent)}%
    </span>
  );
}

/** Compact score + micro bar used in tables. */
export function ScoreCell({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));

  return (
    <span className="score-cell">
      <span className="score-bar">
        <span style={{ width: `${clamped}%` }} />
      </span>
      <strong>{clamped}</strong>
    </span>
  );
}

/* ------------------------------------------------------------------ *
 * Company identity mark
 *
 * Derived strictly from the company domain returned by the API — no
 * per-company mapping and no API token. Two tokenless favicon services
 * are tried in order; when neither resolves, a generated single-letter
 * mark with a deterministic colour is used instead.
 * ------------------------------------------------------------------ */

export function logoColor(seed: string): string {
  let hash = 0;
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) % 360;
  }
  return `hsl(${hash} 34% 42%)`;
}

/** Placeholder/example domains never resolve to a real logo. */
function isPlaceholderDomain(domain: string): boolean {
  if (!domain.includes(".")) return true;
  if (domain === "example.com" || domain === "example.org" || domain === "example.net") return true;
  if (domain.endsWith(".example") || domain.endsWith(".test") || domain.endsWith(".localhost")) return true;
  return false;
}

function logoSources(domain: string): string[] {
  return [
    `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128`,
    `https://icons.duckduckgo.com/ip3/${encodeURIComponent(domain)}.ico`,
  ];
}

export function CompanyLogo({
  name,
  domain,
  className = "",
  eager = false,
}: {
  className?: string;
  domain: string | null | undefined;
  eager?: boolean;
  name: string | null | undefined;
}) {
  const cleanDomain = (domain ?? "")
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/^www\./, "")
    .split("/")[0];

  const sources = cleanDomain ? logoSources(cleanDomain) : [];
  const [attempt, setAttempt] = useState(0);
  // Reset the fallback chain when the domain changes so a previous domain's
  // failed loads don't skip this domain's sources.
  const [lastDomain, setLastDomain] = useState(cleanDomain);
  if (lastDomain !== cleanDomain) {
    setLastDomain(cleanDomain);
    setAttempt(0);
  }
  const usable = Boolean(cleanDomain) && !isPlaceholderDomain(cleanDomain) && attempt < sources.length;

  const letter = ((name ?? "").trim() || cleanDomain || "?").charAt(0).toUpperCase() || "?";

  if (usable) {
    return (
      <span className={`company-logo ${className}`.trim()} aria-hidden="true">
        <img
          alt=""
          decoding="async"
          loading={eager ? "eager" : "lazy"}
          onError={() => setAttempt((value) => value + 1)}
          referrerPolicy="no-referrer"
          src={sources[attempt]}
        />
      </span>
    );
  }

  return (
    <span
      aria-hidden="true"
      className={`company-logo ${className}`.trim()}
      style={{ background: logoColor(cleanDomain || letter) }}
    >
      {letter}
    </span>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="notice notice-error" role="alert">
      {message}
    </div>
  );
}

export function SuccessNotice({ message }: { message: string }) {
  return (
    <div className="notice notice-success" role="status">
      {message}
    </div>
  );
}

export function EmptyState({
  title,
  children,
}: {
  children?: ReactNode;
  title: string;
}) {
  return (
    <div className="empty-state">
      <div className="empty-title">{title}</div>

      {children ? (
        <div className="empty-text">{children}</div>
      ) : null}
    </div>
  );
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="empty-state">
      <span className="spinner" />
      <div className="empty-text">{label}…</div>
    </div>
  );
}

/** One cell of a `.runs-summary` strip. */
export function Metric({
  label,
  value,
  hint,
}: {
  hint?: ReactNode;
  label: string;
  value: ReactNode;
}) {
  return (
    <div>
      <span className="summary-label">{label}</span>
      <strong>{value}</strong>

      {hint ? <span className="summary-note">{hint}</span> : null}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  action?: ReactNode;
  description?: string;
  title: string;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>

        {description ? <p>{description}</p> : null}
      </div>

      {action}
    </div>
  );
}

export function SectionTitle({
  title,
  subtitle,
  action,
}: {
  action?: ReactNode;
  subtitle?: string;
  title: string;
}) {
  return (
    <div className="section-title">
      <div>
        <h2>{title}</h2>

        {subtitle ? <p>{subtitle}</p> : null}
      </div>

      {action}
    </div>
  );
}

const CLAMP_THRESHOLD = 320;

/**
 * Display-only cleanup of scraped evidence text: collapses web-scrape
 * artefacts (##### banners, "Description:" prefixes, repeated whitespace)
 * so sources read as evidence rather than raw dumps. The stored value is
 * never modified.
 */
export function cleanExcerpt(text: string): string {
  return text
    .replace(/#{2,}/g, " ")
    .replace(/\s*\bDescription:\s*/gi, " ")
    .replace(/[“”`]{2,}/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** Display-only: drops the agent's internal "(intelligence.field)" grounding notes. */
export function stripGroundingNote(claim: string): string {
  return claim.replace(/\s*\((?:intelligence|evidence)[^)]*\)\s*\.?$/i, "").trim() || claim.trim();
}

export function EvidenceExcerpt({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const cleaned = cleanExcerpt(text);
  const canToggle = cleaned.length > CLAMP_THRESHOLD;

  return (
    <div>
      <p
        className={`evidence-excerpt${canToggle && !expanded ? " is-clamped" : ""}`}
      >
        {cleaned}
      </p>

      {canToggle ? (
        <button
          className="link-btn"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      ) : null}
    </div>
  );
}
