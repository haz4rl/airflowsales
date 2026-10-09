"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import {
  CompanyLogo,
  ConfidenceValue,
  DecisionBadge,
  EmptyState,
  ErrorNotice,
  EvidenceExcerpt,
  LoadingBlock,
  StatusBadge,
  SuccessNotice,
  humanize,
  stripGroundingNote,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  displayCompany,
  formatDate,
  formatRelative,
  numericEntries,
  otherEntries,
  stringifyValue,
} from "@/lib/format";
import type { WorkflowRunListItem } from "@/lib/types";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function hostOf(url: string): string | null {
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

function formatLatency(latencyMs: number | null): string | null {
  if (!latencyMs || latencyMs < 50) return null;
  return latencyMs >= 1000 ? `${(latencyMs / 1000).toFixed(1)}s` : `${latencyMs}ms`;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === "string" && entry.trim() !== "")
    : [];
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function NotFound() {
  return (
    <>
      <Link className="back-link" href="/prospects">
        <ArrowLeft />
        Back to prospect list
      </Link>

      <div className="not-found">
        <h1>Prospect not found</h1>
        <p>
          This prospect does not exist, or the link points at the wrong record. The prospect
          list shows everything that has been researched so far.
        </p>
        <Link className="primary-button" href="/prospects">
          Open prospect list
        </Link>
      </div>
    </>
  );
}

export default function ProspectDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const validId = UUID_PATTERN.test(id);

  const prospectQuery = useApi(() => api.getProspect(id), [id], validId);
  const runsQuery = useApi(() => api.listRuns({ prospectId: id }), [id], validId);
  const campaignsQuery = useApi(() => api.listCampaigns(), []);
  const [approvalNotice, setApprovalNotice] = useState<string | null>(null);

  const runs = runsQuery.data ?? [];
  const latestRunId = runs[0]?.id ?? null;
  const runDetailQuery = useApi(() => api.getRun(latestRunId ?? ""), [latestRunId], Boolean(latestRunId));

  const pendingRun: WorkflowRunListItem | undefined = runs.find(
    (run) => run.status === "AWAITING_APPROVAL",
  );

  const events = runDetailQuery.data?.events ?? [];
  // The revision loop can replace the draft and the review: show the final
  // state, which lives in the last outreach_*/critic_* event.
  const outreachEvent = [...events]
    .reverse()
    .find((event) => event.name === "outreach_agent" || event.name === "outreach_revision");
  const criticEvent = [...events]
    .reverse()
    .find((event) => event.name === "critic_agent" || event.name === "critic_revision");

  const outreach = outreachEvent?.output ?? null;
  const critic = criticEvent?.output ?? null;

  const draft = useMemo(
    () => ({
      subject: stringOrNull(outreach?.subject),
      body: stringOrNull(outreach?.body),
      claims: stringList(outreach?.claims),
      latency: outreachEvent?.latency_ms ?? null,
    }),
    [outreach, outreachEvent],
  );

  const review = useMemo(
    () => ({
      approved: critic?.approved === true,
      checked: Boolean(critic),
      unsupported: stringList(critic?.unsupported_claims),
      notes: stringOrNull(critic?.notes),
      latency: criticEvent?.latency_ms ?? null,
    }),
    [critic, criticEvent],
  );

  function handleApprovalCompleted() {
    setApprovalNotice("Decision recorded — the run and prospect have been updated.");
    prospectQuery.reload();
    runsQuery.reload();
    runDetailQuery.reload();
  }

  if (!validId) return <NotFound />;

  if (prospectQuery.loading && !prospectQuery.data) {
    return <LoadingBlock label="Loading prospect" />;
  }

  if (prospectQuery.error && !prospectQuery.data) {
    if (/not found|status 40[44]|status 422/.test(prospectQuery.error)) return <NotFound />;

    return (
      <>
        <ErrorNotice message={prospectQuery.error} />
        <div className="heading-actions">
          <button className="secondary-button" onClick={prospectQuery.reload} type="button">
            Retry
          </button>
          <Link className="secondary-button" href="/prospects">
            Back to prospects
          </Link>
        </div>
      </>
    );
  }

  const data = prospectQuery.data;
  if (!data) return <NotFound />;

  const qualification = data.qualification;
  const numeric = qualification ? numericEntries(qualification.scoring_breakdown) : [];
  const others = qualification ? otherEntries(qualification.scoring_breakdown) : [];
  const maxAbsolute = numeric.length
    ? Math.max(...numeric.map(([, value]) => Math.abs(value)), 1)
    : 1;

  const company = displayCompany(data.company.name, data.company.domain);
  const campaignName =
    (campaignsQuery.data ?? []).find((entry) => entry.id === data.prospect.campaign_id)?.name ??
    null;
  const evidenceCount = data.evidence.length;

  return (
    <>
      <Link className="back-link" href="/prospects">
        <ArrowLeft />
        Back to prospect list
      </Link>

      <div className="detail-head">
        <CompanyLogo
          domain={data.company.domain}
          eager
          name={data.company.name}
          className="large"
        />

        <div className="detail-identity">
          <div className="eyebrow">
            {campaignName ? <span>{campaignName}</span> : null}
            <StatusBadge status={data.prospect.status} />
            {qualification ? <DecisionBadge decision={qualification.decision} /> : null}
          </div>

          <h1>{company}</h1>

          <p>
            {data.company.domain}
            {data.company.industry ? ` · ${data.company.industry}` : ""}
            {data.company.location ? ` · ${data.company.location}` : ""}
          </p>
        </div>

        <div className="detail-actions">
          <button
            className="secondary-button"
            disabled={prospectQuery.loading}
            onClick={prospectQuery.reload}
            type="button"
          >
            <RefreshCw />
            Refresh
          </button>

          {latestRunId ? (
            <Link className="secondary-button" href={`/runs/${latestRunId}`}>
              <ExternalLink />
              Open workflow run
            </Link>
          ) : null}
        </div>
      </div>

      {approvalNotice ? <SuccessNotice message={approvalNotice} /> : null}

      {campaignsQuery.error && !campaignName ? (
        <ErrorNotice message={`Could not load campaign names: ${campaignsQuery.error}`} />
      ) : null}

      <div className="detail-grid">
        <section className="detail-main">
          <div className="section-title">
            <div>
              <h2>Qualification</h2>
              <p>Scored by the qualification agent against this campaign.</p>
            </div>
            {qualification ? <ConfidenceValue value={qualification.confidence} /> : null}
          </div>

          {qualification ? (
            <div className="reasoning-box">
              <div className="reasoning-score">
                <strong>{qualification.score}</strong>
                <span>
                  qualification
                  <br />
                  score
                </span>
              </div>

              <div className="reasoning-body">
                <div className="critic-verdict" style={{ marginBottom: 8 }}>
                  <DecisionBadge decision={qualification.decision} />
                  <span className="tiny faint">
                    {Math.round(
                      qualification.confidence <= 1
                        ? qualification.confidence * 100
                        : qualification.confidence,
                    )}
                    % confidence
                  </span>
                </div>
                <p style={{ marginBottom: 0 }}>
                  {qualification.reasoning?.trim() || "No reasoning recorded."}
                </p>
              </div>
            </div>
          ) : (
            <div className="reasoning-box">
              <div className="reasoning-body">
                <p className="value-none">
                  No qualification has been recorded for this prospect yet.
                </p>
              </div>
            </div>
          )}

          <div className="section-title">
            <div>
              <h2>Evidence and sources</h2>
              <p>
                {evidenceCount} persisted source{evidenceCount === 1 ? "" : "s"} used for
                research.
              </p>
            </div>
          </div>

          {evidenceCount === 0 ? (
            <EmptyState title="No evidence stored" />
          ) : (
            <div className="evidence-list">
              {data.evidence.map((item) => (
                <article className="evidence-row" key={item.id}>
                  <div className="evidence-icon">
                    <ShieldCheck />
                  </div>

                  <div className="evidence-body">
                    <strong>
                      {item.source_url ? (
                        <a
                          className="evidence-link"
                          href={item.source_url}
                          rel="noopener noreferrer"
                          target="_blank"
                        >
                          {item.source_title || item.source_url}
                        </a>
                      ) : (
                        item.source_title || "Untitled source"
                      )}
                    </strong>

                    <EvidenceExcerpt text={item.excerpt} />

                    <div className="evidence-meta">
                      <span className="chip">{humanize(item.evidence_type)}</span>
                      <span className="tiny faint">{formatDate(item.created_at)}</span>
                      {item.source_url && hostOf(item.source_url) ? (
                        <span className="tiny faint mono truncate">{hostOf(item.source_url)}</span>
                      ) : null}
                    </div>
                  </div>

                  {item.source_url ? (
                    <a
                      aria-label="Open source"
                      className="evidence-open"
                      href={item.source_url}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      <ExternalLink />
                    </a>
                  ) : null}
                </article>
              ))}
            </div>
          )}

          <div className="section-title">
            <div>
              <h2>Outreach draft</h2>
              <p>
                {draft.body
                  ? `Drafted by the outreach agent${formatLatency(draft.latency) ? ` in ${formatLatency(draft.latency)}` : ""}.`
                  : "No draft has been produced for this prospect."}
              </p>
            </div>
            {latestRunId ? (
              <Link className="secondary-button" href={`/runs/${latestRunId}`}>
                View run
                <ExternalLink />
              </Link>
            ) : null}
          </div>

          {draft.body ? (
            <div>
              {draft.subject ? (
                <p className="draft-subject">
                  <span>Subject</span>
                  <strong>{draft.subject}</strong>
                </p>
              ) : null}

              <div className="message-box">{draft.body}</div>

              {draft.claims.length > 0 ? (
                <>
                  <p className="tiny faint" style={{ marginTop: 14, marginBottom: 8 }}>
                    Claims the agent was allowed to make
                  </p>
                  <ul className="claim-list">
                    {draft.claims.map((claim) => (
                      <li key={claim}>
                        <span>{stripGroundingNote(claim)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          ) : runDetailQuery.loading ? (
            <LoadingBlock label="Loading latest run" />
          ) : runDetailQuery.error ? (
            <ErrorNotice
              message={`Could not load the latest workflow run: ${runDetailQuery.error}`}
            />
          ) : (
            <EmptyState title="No outreach draft yet">
              The outreach agent writes a draft once a workflow run reaches that stage.
            </EmptyState>
          )}

          <div className="section-title">
            <div>
              <h2>Critic review</h2>
              <p>
                {review.checked
                  ? "Every claim in the draft was checked against the collected evidence."
                  : "The critic agent checks the draft after it is written."}
              </p>
            </div>
          </div>

          {!review.checked ? (
            <EmptyState title="No critic review yet">
              A review appears here once a run completes the critic stage.
            </EmptyState>
          ) : (
            <div className="panel">
              <div className="critic-verdict">
                {review.approved ? (
                  <>
                    <span className="status approved">
                      <ShieldCheck />
                      Approved
                    </span>
                    <span className="tiny faint">
                      Every claim is supported by evidence
                      {formatLatency(review.latency) ? ` · checked in ${formatLatency(review.latency)}` : ""}.
                    </span>
                  </>
                ) : (
                  <>
                    <span className="status awaiting-approval">
                      <TriangleAlert />
                      Unsupported claims
                    </span>
                    <span className="tiny faint">
                      The draft was not approved as written
                      {formatLatency(review.latency) ? ` · checked in ${formatLatency(review.latency)}` : ""}.
                    </span>
                  </>
                )}
              </div>

              {review.unsupported.length > 0 ? (
                <>
                  <p className="tiny faint" style={{ marginBottom: 8 }}>
                    Flagged in the draft
                  </p>
                  <ul className="claim-list">
                    {review.unsupported.map((claim) => (
                      <li key={claim}>
                        <TriangleAlert />
                        <span>{stripGroundingNote(claim)}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}

              {review.notes ? <p className="event-text">{review.notes}</p> : null}
            </div>
          )}
        </section>

        <aside className="detail-side">
          <div className="side-panel">
            <h3>Score breakdown</h3>
            {qualification ? (
              numeric.length === 0 && others.length === 0 ? (
                <p className="tiny faint">No breakdown recorded for this qualification.</p>
              ) : (
                <>
                  {numeric.map(([label, value]) => (
                    <div className="breakdown" key={label}>
                      <div className="breakdown-row">
                        <span>{humanize(label)}</span>
                        <strong className={value < 0 ? "negative" : undefined}>{value}</strong>
                      </div>
                      <div className="breakdown-bar">
                        <span
                          className={value < 0 ? "negative" : undefined}
                          style={{
                            width: `${Math.min(100, (Math.abs(value) / maxAbsolute) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}

                  {others.length > 0 ? (
                    <div className="evidence-meta">
                      {others.map(([label, value]) => (
                        <span className="chip" key={label}>
                          {humanize(label)}: {stringifyValue(value)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </>
              )
            ) : (
              <p className="tiny faint">Not qualified yet.</p>
            )}
          </div>

          <div className="side-panel">
            <h3>Company record</h3>
            <dl className="kv">
              <dt>Legal name</dt>
              <dd>{data.company.name ?? "—"}</dd>
              <dt>Domain</dt>
              <dd className="mono">{data.company.domain}</dd>
              <dt>Industry</dt>
              <dd>{data.company.industry ?? "—"}</dd>
              <dt>Location</dt>
              <dd>{data.company.location ?? "—"}</dd>
              <dt>Description</dt>
              <dd>{data.company.description ?? "—"}</dd>
              <dt>Created</dt>
              <dd>{formatDate(data.prospect.created_at)}</dd>
            </dl>
          </div>

          <div className="side-panel">
            <h3>Workflow activity ({runs.length})</h3>

            {runsQuery.loading ? (
              <LoadingBlock label="Loading runs" />
            ) : runsQuery.error ? (
              <ErrorNotice message={runsQuery.error} />
            ) : runs.length === 0 ? (
              <p className="tiny faint">No runs recorded for this prospect.</p>
            ) : (
              <div className="timeline">
                {runs.map((run) => (
                  <div key={run.id}>
                    <span
                      className={`timeline-dot ${run.status === "FAILED" ? "error" : "done"}`}
                    />

                    <div className="timeline-body">
                      <p>
                        <strong>
                          <Link href={`/runs/${run.id}`}>{humanize(run.status)}</Link>
                        </strong>
                        <small>
                          {formatRelative(run.created_at)} · {run.event_count} event
                          {run.event_count === 1 ? "" : "s"} ·{" "}
                          {run.total_tokens.toLocaleString()} tokens
                        </small>
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {pendingRun ? (
            <div className="side-panel">
              <h3>Human approval</h3>
              <p className="tiny faint" style={{ marginTop: -8, marginBottom: 12 }}>
                This run is waiting for a decision before it continues.
              </p>
              <ApprovalPanel runId={pendingRun.id} onCompleted={handleApprovalCompleted} />
            </div>
          ) : null}
        </aside>
      </div>
    </>
  );
}
