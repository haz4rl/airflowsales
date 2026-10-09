"use client";

import type { ReactNode } from "react";
import type { WorkflowEvent } from "@/lib/types";
import { humanize, stripGroundingNote } from "./ui";
import { formatDate, stringifyValue } from "@/lib/format";

const LABELS: Record<string, string> = {
  company_search: "Company search",
  research_agent: "Research agent",
  qualification_agent: "Qualification agent",
  outreach_agent: "Outreach agent",
  critic_agent: "Critic agent",
  outreach_revision: "Outreach revised",
  critic_revision: "Critic re-review",
  workflow_failure: "Run stopped",
  approval: "Approval decision",
};

function labelFor(event: WorkflowEvent): string {
  const known = LABELS[event.name];
  if (known) return known;
  if (event.name.endsWith("_retry")) return `${humanize(event.name.replace(/_retry$/, ""))} retried`;
  return humanize(event.name);
}

function tokensFor(event: WorkflowEvent): number | null {
  const value = event.token_usage?.["total_tokens"];
  return typeof value === "number" ? value : null;
}

function dotTone(event: WorkflowEvent): string {
  if (event.event_type === "ERROR") return "timeline-dot error";
  if (event.event_type === "RETRY") return "timeline-dot alert";
  return "timeline-dot done";
}

function latency(latencyMs: number | null): string | null {
  if (!latencyMs) return null;
  return latencyMs >= 1000 ? `${(latencyMs / 1000).toFixed(1)}s` : `${latencyMs}ms`;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === "string" && entry.trim() !== "")
    : [];
}

function facts(entries: Array<[string, ReactNode]>): ReactNode {
  const present = entries.filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (present.length === 0) return null;

  return (
    <div className="event-facts">
      {present.map(([label, value]) => (
        <div className="event-fact" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function eventContent(event: WorkflowEvent): ReactNode {
  const out = event.output ?? {};

  if (event.name === "company_search") {
    return facts([
      ["Domain", text(event.input?.["domain"]) ?? "—"],
      ["Results", number(out["results"]) !== null ? `${number(out["results"])} sources` : null],
    ]);
  }

  if (event.name === "research_agent") {
    return (
      <>
        {facts([
          ["Industry", text(out["industry"]) ?? "—"],
          ["Location", text(out["location"]) ?? "—"],
          ["Evidence used", number(event.input?.["evidence_count"])],
        ])}
        {text(out["description"]) ? <p className="event-text">{text(out["description"])}</p> : null}
      </>
    );
  }

  if (event.name === "qualification_agent") {
    const confidence = number(out["confidence"]);
    return (
      <>
        {facts([
          ["Score", number(out["score"])],
          ["Decision", text(out["decision"]) ? humanize(String(out["decision"])) : "—"],
          [
            "Confidence",
            confidence === null ? null : `${Math.round(confidence <= 1 ? confidence * 100 : confidence)}%`,
          ],
        ])}
        {text(out["reasoning"]) ? <p className="event-text">{text(out["reasoning"])}</p> : null}
      </>
    );
  }

  if (event.name === "outreach_agent" || event.name === "outreach_revision") {
    const claims = stringList(out["claims"]);
    return (
      <>
        {text(out["subject"]) ? (
          <p className="draft-subject">
            <span>Subject</span>
            <strong>{text(out["subject"])}</strong>
          </p>
        ) : null}
        {text(out["body"]) ? <p className="event-text strong">{text(out["body"])}</p> : null}
        {claims.length > 0 ? (
          <p className="tiny faint" style={{ marginTop: 8 }}>
            {claims.length} grounded claim{claims.length === 1 ? "" : "s"} requested from the agent.
          </p>
        ) : null}
      </>
    );
  }

  if (event.name === "critic_agent" || event.name === "critic_revision") {
    const unsupported = stringList(out["unsupported_claims"]);
    return (
      <>
        <div className="critic-verdict">
          <span className={`status ${out["approved"] === true ? "approved" : "awaiting-approval"}`}>
            {out["approved"] === true ? "Approved" : "Unsupported claims"}
          </span>
        </div>
        {unsupported.length > 0 ? (
          <ul className="claim-list">
            {unsupported.map((claim) => (
              <li key={claim}>
                <span>{stripGroundingNote(claim)}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {text(out["notes"]) ? <p className="event-text">{text(out["notes"])}</p> : null}
      </>
    );
  }

  if (event.name === "approval") {
    return facts([
      ["Decision", event.output?.["approved"] === true ? "Approved" : "Rejected"],
      ["Note", text(event.input?.["note"]) ?? "—"],
    ]);
  }

  if (event.event_type === "RETRY") {
    const detail = text(out["detail"]) ?? text(out["reason"]);
    const attempt = number(out["retry"]);
    return (
      <p className="event-text">
        {attempt !== null ? `Attempt ${attempt}` : "Attempt"}
        {detail ? ` failed: ${detail}` : " failed"} · retrying after{" "}
        {number(out["delay_seconds"]) ?? 0}s.
      </p>
    );
  }

  if (event.event_type === "ERROR") {
    return <p className="event-text strong">{text(out["error"]) ?? "The run stopped unexpectedly."}</p>;
  }

  if (Object.keys(out).length > 0) {
    return <pre className="json-block">{stringifyValue(out)}</pre>;
  }

  return null;
}

export function Timeline({ events }: { events: WorkflowEvent[] }) {
  const ordered = [...events].sort((a, b) => a.created_at.localeCompare(b.created_at));

  return (
    <div className="timeline">
      {ordered.map((event) => {
        const tokens = tokensFor(event);
        const taken = latency(event.latency_ms);
        const meta = [taken, tokens !== null ? `${tokens} tokens` : null, formatDate(event.created_at)]
          .filter(Boolean)
          .join(" · ");
        const content = eventContent(event);

        return (
          <div key={event.id}>
            <span className={dotTone(event)} />

            <div className="timeline-body">
              <p>
                <strong>{labelFor(event)}</strong>

                <small>
                  <span className={`chip chip-${event.event_type.toLowerCase()}`}>
                    {event.event_type}
                  </span>
                  {meta}
                </small>
              </p>

              {content ? <div className="event-card">{content}</div> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
