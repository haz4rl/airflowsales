"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, RefreshCw } from "lucide-react";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { Timeline } from "@/components/Timeline";
import {
  CompanyLogo,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  Metric,
  StatusBadge,
  SuccessNotice,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { durationBetween, formatDate, formatDuration, formatNumber } from "@/lib/format";
import type { WorkflowRun } from "@/lib/types";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function NotFound() {
  return (
    <>
      <Link className="back-link" href="/runs">
        <ArrowLeft />
        Back to workflow runs
      </Link>

      <div className="not-found">
        <h1>Workflow run not found</h1>
        <p>
          This run does not exist, or the link points at the wrong record. The run list shows
          every discovery the agents have executed.
        </p>
        <Link className="primary-button" href="/runs">
          Open run list
        </Link>
      </div>
    </>
  );
}

export default function WorkflowRunPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const validId = UUID_PATTERN.test(id);

  const { data: run, error, loading, reload } = useApi(() => api.getRun(id), [id], validId);
  const prospectQuery = useApi(
    () => api.getProspect(run?.prospect_id ?? ""),
    [run?.prospect_id],
    Boolean(run?.prospect_id),
  );
  const [notice, setNotice] = useState<string | null>(null);

  // Live clock so an in-flight run shows ticking elapsed time.
  const [now, setNow] = useState(() => Date.now());
  const isRunning = run?.status === "RUNNING";
  useEffect(() => {
    if (!isRunning) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isRunning]);

  function handleApprovalCompleted(updated: WorkflowRun) {
    setNotice(
      updated.status === "APPROVED"
        ? "Approval recorded — this run and its prospect are now marked approved."
        : "Rejection recorded — this run and its prospect are now marked rejected.",
    );
    reload();
    prospectQuery.reload();
  }

  if (!validId) return <NotFound />;

  if (loading && !run) return <LoadingBlock label="Loading workflow run" />;

  if (error && !run) {
    if (/not found|status 40[44]|status 422/.test(error)) return <NotFound />;

    return (
      <>
        <ErrorNotice message={error} />
        <div className="heading-actions">
          <button className="secondary-button" onClick={reload} type="button">
            Retry
          </button>
          <Link className="secondary-button" href="/runs">
            All workflow runs
          </Link>
        </div>
      </>
    );
  }

  if (!run) return <NotFound />;

  const retries = run.events.filter((event) => event.event_type === "RETRY").length;
  const errors = run.events.filter((event) => event.event_type === "ERROR").length;
  const duration =
    run.status === "RUNNING"
      ? Math.max(0, now - Date.parse(run.created_at))
      : durationBetween(run.created_at, run.updated_at);

  const company = prospectQuery.data?.company ?? null;
  const companyTitle = company ? company.name ?? company.domain : "Workflow run";

  return (
    <>
      <Link className="back-link" href="/runs">
        <ArrowLeft />
        Back to workflow runs
      </Link>

      <div className="detail-head">
        <CompanyLogo
          domain={company?.domain ?? null}
          eager
          name={company?.name ?? null}
          className="large"
        />

        <div className="detail-identity">
          <div className="eyebrow">
            <span>Workflow run</span>
            <StatusBadge status={run.status} />
          </div>

          <h1>{companyTitle}</h1>

          <p>
            {company?.domain ?? "Company record unavailable"}
            {company?.industry ? ` · ${company.industry}` : ""} · started{" "}
            {formatDate(run.created_at)}
          </p>
        </div>

        <div className="detail-actions">
          <button className="secondary-button" disabled={loading} onClick={reload} type="button">
            <RefreshCw />
            Refresh
          </button>

          <Link className="secondary-button" href={`/prospects/${run.prospect_id}`}>
            <ExternalLink />
            Open prospect
          </Link>
        </div>
      </div>

      {notice ? <SuccessNotice message={notice} /> : null}

      {prospectQuery.error && !company ? (
        <ErrorNotice message={`Could not load the linked prospect: ${prospectQuery.error}`} />
      ) : null}

      <div className="runs-summary">
        <Metric
          hint={
            errors || retries
              ? `${errors} failure${errors === 1 ? "" : "s"} · ${retries} retr${
                  retries === 1 ? "y" : "ies"
                }`
              : "no failures or retries"
          }
          label="Events"
          value={formatNumber(run.events.length)}
        />
        <Metric
          hint={
            run.total_cost > 0
              ? `≈ $${run.total_cost.toFixed(4)} estimated`
              : "no cost recorded"
          }
          label="Tokens"
          value={formatNumber(run.total_tokens)}
        />
        <Metric
          hint={
            run.status === "RUNNING"
              ? `in progress · started ${formatDate(run.created_at)}`
              : `finished ${formatDate(run.updated_at)}`
          }
          label={run.status === "RUNNING" ? "Elapsed" : "Duration"}
          value={formatDuration(duration)}
        />
      </div>

      <div className="detail-grid">
        <section className="detail-main">
          <div className="section-title">
            <div>
              <h2>Execution timeline</h2>
              <p>Search, research, qualification, outreach and review in execution order.</p>
            </div>
          </div>

          {run.events.length === 0 ? (
            <EmptyState title="No events recorded" />
          ) : (
            <Timeline events={run.events} />
          )}
        </section>

        <aside className="detail-side">
          <div className="side-panel">
            <h3>Run record</h3>
            <dl className="kv">
              <dt>Status</dt>
              <dd>
                <StatusBadge status={run.status} />
              </dd>
              <dt>Prospect</dt>
              <dd>
                <Link className="evidence-link" href={`/prospects/${run.prospect_id}`}>
                  {companyTitle}
                </Link>
              </dd>
              <dt>Run id</dt>
              <dd className="mono" title={run.id}>
                {run.id.slice(0, 8)}…
              </dd>
              <dt>Started</dt>
              <dd>{formatDate(run.created_at)}</dd>
              <dt>Updated</dt>
              <dd>{formatDate(run.updated_at)}</dd>
            </dl>
          </div>

          {run.status === "AWAITING_APPROVAL" ? (
            <div className="side-panel">
              <h3>Human approval</h3>
              <p className="tiny faint" style={{ marginTop: -8, marginBottom: 12 }}>
                Approving or rejecting updates this run and its prospect.
              </p>
              <ApprovalPanel runId={run.id} onCompleted={handleApprovalCompleted} />
            </div>
          ) : null}
        </aside>
      </div>
    </>
  );
}
