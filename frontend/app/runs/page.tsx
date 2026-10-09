"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ArrowUpDown, ChevronRight, Plus, RefreshCw, Search, X } from "lucide-react";
import {
  CompanyLogo,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  formatDate,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRelative,
} from "@/lib/format";
import type { WorkflowRunListItem } from "@/lib/types";

type SortKey = "company" | "duration" | "events" | "started" | "status" | "tokens";

interface SortState {
  dir: "asc" | "desc";
  key: SortKey;
}

const SORT_LABEL: Record<SortKey, string> = {
  company: "Company",
  duration: "Duration",
  events: "Events",
  started: "Started",
  status: "Status",
  tokens: "Tokens",
};

function durationMs(run: WorkflowRunListItem): number {
  return Date.parse(run.updated_at) - Date.parse(run.created_at);
}

export default function WorkflowRunsPage() {
  const router = useRouter();
  const { data: runs, error, loading, reload } = useApi(() => api.listRuns({ limit: 500 }), []);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [sort, setSort] = useState<SortState>({ key: "started", dir: "desc" });

  // Live clock so in-flight runs show a ticking elapsed time instead of a
  // frozen updated_at delta.
  const [now, setNow] = useState(() => Date.now());
  const hasRunning = useMemo(() => (runs ?? []).some((run) => run.status === "RUNNING"), [runs]);
  useEffect(() => {
    if (!hasRunning) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [hasRunning]);

  const rows = useMemo(() => {
    const list = runs ?? [];
    const needle = query.trim().toLowerCase();
    const filtered = list.filter((item) => {
      if (statusFilter !== "ALL" && item.status !== statusFilter) return false;
      if (!needle) return true;
      return `${item.company_name ?? ""} ${item.company_domain ?? ""}`
        .toLowerCase()
        .includes(needle);
    });

    const { dir, key } = sort;
    return [...filtered].sort((a, b) => {
      const av = key === "duration" ? durationMs(a) : sortValue(a, key);
      const bv = key === "duration" ? durationMs(b) : sortValue(b, key);
      const result =
        typeof av === "number" && typeof bv === "number"
          ? av - bv
          : String(av).localeCompare(String(bv));
      if (result !== 0) return dir === "asc" ? result : -result;
      return a.id.localeCompare(b.id);
    });
  }, [runs, query, statusFilter, sort]);

  const statusOptions = useMemo(() => {
    const values = new Set((runs ?? []).map((item) => item.status));
    return [...values].sort();
  }, [runs]);

  const stats = useMemo(() => {
    const list = runs ?? [];
    const total = list.length;
    const completed = list.filter((run) => run.status === "COMPLETED").length;
    const failed = list.filter((run) => run.status === "FAILED").length;
    const durations = list
      .filter((run) => run.status === "COMPLETED" || run.status === "FAILED")
      .map(durationMs)
      .filter((value) => Number.isFinite(value) && value >= 0);
    const avg = durations.length
      ? durations.reduce((sum, value) => sum + value, 0) / durations.length
      : null;
    return {
      avg,
      completed,
      failed,
      finished: durations.length,
      successRate: total ? completed / total : null,
      total,
    };
  }, [runs]);

  function elapsedMs(run: WorkflowRunListItem): number {
    if (run.status === "RUNNING") return Math.max(0, now - Date.parse(run.created_at));
    return durationMs(run);
  }

  const total = runs?.length ?? 0;
  const filtersActive = query.trim() !== "" || statusFilter !== "ALL";

  function clearFilters() {
    setQuery("");
    setStatusFilter("ALL");
  }

  return (
    <>
      <PageHeader
        action={
          <div className="heading-actions">
            <button className="secondary-button" disabled={loading} onClick={reload} type="button">
              {loading ? <span className="spinner" /> : <RefreshCw />}
              Refresh
            </button>
            <Link className="primary-button" href="/discover">
              <Plus />
              Discover prospect
            </Link>
          </div>
        }
        description="Every discovery run, with the stage it reached, how long it took and what it cost in tokens."
        title="Workflow runs"
      />

      <div className="runs-summary">
        <div>
          <span className="summary-label">Completed</span>
          <strong>{stats.completed}</strong>
          <span className="summary-note">
            {stats.successRate === null
              ? "no runs recorded yet"
              : `${formatPercent(stats.successRate, 1)} of ${stats.total} ${
                  stats.total === 1 ? "run" : "runs"
                } finished cleanly`}
          </span>
        </div>
        <div>
          <span className="summary-label">Failed</span>
          <strong>{stats.failed}</strong>
          <span className="summary-note">
            {stats.failed === 0
              ? "no failed runs"
              : `${formatPercent(stats.failed / stats.total, 1)} of ${stats.total} ${
                  stats.total === 1 ? "run" : "runs"
                } failed`}
          </span>
        </div>
        <div>
          <span className="summary-label">Avg. duration</span>
          <strong>{stats.avg === null ? "—" : formatDuration(stats.avg)}</strong>
          <span className="summary-note">
            across {stats.finished} finished {stats.finished === 1 ? "run" : "runs"}
          </span>
        </div>
      </div>

      <div className="workspace-toolbar">
        <div className="search-box">
          <Search />
          <input
            aria-label="Search runs"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search company"
            value={query}
          />
          {query ? (
            <button aria-label="Clear search" onClick={() => setQuery("")} type="button">
              <X />
            </button>
          ) : null}
        </div>

        <div className="toolbar-divider" />

        <select
          aria-label="Filter by status"
          className={`toolbar-select${statusFilter !== "ALL" ? " filled" : ""}`}
          onChange={(event) => setStatusFilter(event.target.value)}
          value={statusFilter}
        >
          <option value="ALL">All statuses</option>
          {statusOptions.map((status) => (
            <option key={status} value={status}>
              {status.replace(/_/g, " ")}
            </option>
          ))}
        </select>

        {filtersActive ? (
          <button className="toolbar-button" onClick={clearFilters} type="button">
            <X />
            Clear
          </button>
        ) : null}

        <div className="toolbar-spacer" />

        <select
          aria-label="Sort by"
          className="toolbar-select"
          onChange={(event) =>
            setSort((current) => ({ ...current, key: event.target.value as SortKey }))
          }
          value={sort.key}
        >
          {(Object.keys(SORT_LABEL) as SortKey[]).map((key) => (
            <option key={key} value={key}>
              Sort: {SORT_LABEL[key]}
            </option>
          ))}
        </select>
        <button
          aria-label={`Sort direction, currently ${sort.dir === "asc" ? "ascending" : "descending"}`}
          className="toolbar-button"
          onClick={() =>
            setSort((current) => ({ ...current, dir: current.dir === "asc" ? "desc" : "asc" }))
          }
          type="button"
        >
          <ArrowUpDown />
          {sort.dir === "asc" ? "Ascending" : "Descending"}
        </button>
      </div>

      <div className="table-meta">
        <span>
          <strong>{rows.length}</strong> of {total} {total === 1 ? "run" : "runs"}
        </span>
        <span className="meta-dot" />
        <span>
          Sorted by {SORT_LABEL[sort.key].toLowerCase()} ·{" "}
          {sort.dir === "asc" ? "ascending" : "descending"}
        </span>
      </div>

      {error && !runs ? (
        <>
          <ErrorNotice message={error} />
          <button className="secondary-button" onClick={reload} type="button">
            Retry
          </button>
        </>
      ) : loading && !runs ? (
        <LoadingBlock label="Loading runs" />
      ) : total === 0 ? (
        <EmptyState title="No workflow runs yet">
          Runs appear here as soon as a discovery completes.{" "}
          <Link className="evidence-link" href="/discover">
            Go to discovery
          </Link>
          .
        </EmptyState>
      ) : rows.length === 0 ? (
        <EmptyState title="No matches">
          No run matches the current search or filters.{" "}
          <button className="link-btn" onClick={clearFilters} type="button">
            Clear filters
          </button>
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Company</th>
                <th>Status</th>
                <th className="col-secondary">Duration</th>
                <th className="col-secondary">Events</th>
                <th className="col-secondary">Tokens</th>
                <th className="col-compact">Started</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((run) => (
                <tr
                  className="clickable"
                  key={run.id}
                  onClick={() => router.push(`/runs/${run.id}`)}
                >
                  <td>
                    <div className="company-cell">
                      <CompanyLogo
                        domain={run.company_domain}
                        name={run.company_name ?? run.company_domain}
                      />
                      <div>
                        <strong>
                          <Link className="row-link" href={`/runs/${run.id}`}>
                            {run.company_name ?? run.company_domain ?? "Unknown"}
                          </Link>
                        </strong>
                        <span>{run.company_domain ?? "—"}</span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="col-secondary">
                    {run.status === "RUNNING" ? (
                      <span title="Elapsed since the run started">
                        {formatDuration(elapsedMs(run))} · running
                      </span>
                    ) : (
                      formatDuration(durationMs(run))
                    )}
                  </td>
                  <td className="col-secondary">{formatNumber(run.event_count)}</td>
                  <td className="col-secondary">{formatNumber(run.total_tokens)}</td>
                  <td className="col-compact">
                    <span className="muted-cell" title={formatDate(run.created_at)}>
                      {formatRelative(run.created_at)}
                    </span>
                  </td>
                  <td>
                    <ChevronRight className="table-arrow" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {error && runs ? <ErrorNotice message={error} /> : null}
    </>
  );
}

function sortValue(run: WorkflowRunListItem, key: SortKey): string | number {
  switch (key) {
    case "company":
      return (run.company_name ?? run.company_domain ?? "").toLowerCase();
    case "status":
      return run.status.toLowerCase();
    case "events":
      return run.event_count;
    case "tokens":
      return run.total_tokens;
    case "started":
      return run.created_at;
    case "duration":
      return durationMs(run);
  }
}
