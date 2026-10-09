"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Plus, RefreshCw } from "lucide-react";
import {
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  Metric,
  PageHeader,
  humanize,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatNumber, formatPercent } from "@/lib/format";

function MetricRow({
  hint,
  label,
  value,
}: {
  hint?: string;
  label: string;
  value: string;
}) {
  return (
    <div className="metric-row">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <em className="neutral">{hint}</em> : null}
    </div>
  );
}

export default function AnalyticsPage() {
  const { data: summary, error, loading, reload } = useApi(() => api.dashboard(), []);
  const campaignsQuery = useApi(() => api.listCampaigns(), []);
  const prospectsQuery = useApi(() => api.listProspects({ limit: 500 }), []);
  const campaigns = campaignsQuery.data;
  const prospects = prospectsQuery.data;

  const runStatuses = summary?.run_statuses ?? {};
  const completedRuns = runStatuses["COMPLETED"] ?? 0;
  const failedRuns = runStatuses["FAILED"] ?? 0;
  const runningRuns = runStatuses["RUNNING"] ?? 0;

  const successRate = useMemo(() => {
    if (!summary || summary.workflow_runs === 0) return null;
    return completedRuns / summary.workflow_runs;
  }, [summary, completedRuns]);

  const statusEntries = useMemo(() => {
    if (!summary) return [] as Array<[string, number]>;
    return Object.entries(summary.statuses)
      .filter(([, count]) => count > 0)
      .sort((a, b) => b[1] - a[1]);
  }, [summary]);

  const maxStatus = statusEntries.reduce((max, [, count]) => Math.max(max, count), 0);
  const statusTotal = statusEntries.reduce((sum, [, count]) => sum + count, 0);

  const campaignRows = useMemo(() => {
    return (campaigns ?? []).map((campaign) => {
      const owned = (prospects ?? []).filter((item) => item.prospect.campaign_id === campaign.id);
      const scores = owned
        .map((item) => item.qualification?.score)
        .filter((score): score is number => typeof score === "number");
      const go = owned.filter((item) => item.qualification?.decision === "GO").length;
      return {
        campaign,
        go,
        owned: owned.length,
        score: scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null,
      };
    });
  }, [campaigns, prospects]);

  return (
    <>
      <PageHeader
        action={
          <button className="secondary-button" disabled={loading} onClick={reload} type="button">
            {loading ? <span className="spinner" /> : <RefreshCw />}
            Refresh
          </button>
        }
        description="Prospect outcomes, run reliability and token usage across the workspace."
        title="Analytics"
      />

      {error ? <ErrorNotice message={error} /> : null}
      {campaignsQuery.error ? (
        <ErrorNotice message={`Campaign list failed to load: ${campaignsQuery.error}`} />
      ) : null}
      {prospectsQuery.error ? (
        <ErrorNotice message={`Prospect list failed to load: ${prospectsQuery.error}`} />
      ) : null}

      {loading && !summary ? (
        <LoadingBlock label="Loading summary" />
      ) : summary ? (
        <>
          <div className="runs-summary cols-4">
            <Metric
              hint={`${formatNumber(summary.companies)} ${summary.companies === 1 ? "company" : "companies"} researched`}
              label="Prospects"
              value={formatNumber(summary.prospects)}
            />
            <Metric
              hint="Qualification decision GO"
              label="Qualified"
              value={formatNumber(summary.qualified)}
            />
            <Metric
              hint="Awaiting a human decision"
              label="In review"
              value={formatNumber(summary.awaiting_approval)}
            />
            <Metric
              hint={successRate === null ? "no runs yet" : `${formatNumber(summary.workflow_runs)} runs executed`}
              label="Success rate"
              value={successRate === null ? "—" : formatPercent(successRate, 1)}
            />
          </div>

          <div className="analytics-grid" style={{ marginTop: 26 }}>
            <div className="panel">
              <div className="analytics-side">
                <div className="section-title" style={{ marginBottom: 16 }}>
                  <div>
                    <h2>Prospect status</h2>
                    <p>
                      {formatNumber(statusTotal)} prospect{statusTotal === 1 ? "" : "s"} currently
                      in the pipeline.
                    </p>
                  </div>
                </div>

                {statusEntries.length === 0 ? (
                  <EmptyState title="No prospects yet">
                    Run a discovery to populate this view.
                  </EmptyState>
                ) : (
                  statusEntries.map(([status, count]) => (
                    <div className="outcome-row" key={status}>
                      <span>{humanize(status)}</span>
                      <div className="outcome-bar">
                        <i
                          style={{ width: `${maxStatus ? (count / maxStatus) * 100 : 0}%` }}
                        />
                      </div>
                      <strong>{formatNumber(count)}</strong>
                      <span className="muted-cell">
                        {statusTotal ? formatPercent(count / statusTotal, 0) : "0%"}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="panel">
              <div className="analytics-side">
                <div className="section-title" style={{ marginBottom: 4 }}>
                  <div>
                    <h2>Workflow runs</h2>
                    <p>Execution outcomes across all discovery runs.</p>
                  </div>
                </div>

                <MetricRow
                  hint={summary.workflow_runs === 0 ? "No runs yet" : "All time"}
                  label="Total runs"
                  value={formatNumber(summary.workflow_runs)}
                />
                <MetricRow
                  hint="Runs that finished cleanly"
                  label="Completed"
                  value={formatNumber(completedRuns)}
                />
                <MetricRow
                  hint="Runs that stopped on an error"
                  label="Failed"
                  value={formatNumber(failedRuns)}
                />
                <MetricRow
                  hint={runningRuns ? `${runningRuns} currently in flight` : undefined}
                  label="Tokens used"
                  value={formatNumber(summary.total_tokens)}
                />
              </div>
            </div>
          </div>

          <div className="panel" style={{ marginTop: 26 }}>
            <div className="section-title">
              <div>
                <h2>Campaign coverage</h2>
                <p>What each campaign has researched so far.</p>
              </div>

              <Link className="secondary-button" href="/discover">
                <Plus />
                New discovery
              </Link>
            </div>

            {campaignRows.length === 0 ? (
              <EmptyState title="No campaigns yet">
                <Link className="evidence-link" href="/campaigns">
                  Create a campaign
                </Link>{" "}
                to start researching companies against a market.
              </EmptyState>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Campaign</th>
                      <th>Prospects</th>
                      <th>Qualified (GO)</th>
                      <th>Avg. score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {campaignRows.map(({ campaign, go, owned, score }) => (
                      <tr key={campaign.id}>
                        <td>
                          <strong>{campaign.name}</strong>
                        </td>
                        <td>{formatNumber(owned)}</td>
                        <td>{formatNumber(go)}</td>
                        <td>{score === null ? <span className="faint">—</span> : Math.round(score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : null}
    </>
  );
}
