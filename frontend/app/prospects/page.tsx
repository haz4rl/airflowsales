"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowUpDown, ChevronRight, Plus, RefreshCw, Search, X } from "lucide-react";

import {
  CompanyLogo,
  ConfidenceValue,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  ScoreCell,
  StatusBadge,
} from "@/components/ui";

import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { displayCompany, formatRelative } from "@/lib/format";
import type { ProspectListItem } from "@/lib/types";

type SortKey =
  | "campaign"
  | "company"
  | "confidence"
  | "industry"
  | "research"
  | "score"
  | "status";

interface SortState {
  dir: "asc" | "desc";
  key: SortKey;
}

const SORT_LABEL: Record<SortKey, string> = {
  campaign: "Campaign",
  company: "Company",
  confidence: "Confidence",
  industry: "Industry",
  research: "Last researched",
  score: "Qualification score",
  status: "Status",
};

type CellValue = string | number | null;

function cellValue(item: ProspectListItem, key: SortKey): CellValue {
  switch (key) {
    case "company":
      return displayCompany(item.company.name, item.company.domain).toLowerCase();
    case "industry":
      return (item.company.industry ?? "").toLowerCase();
    case "score":
      return item.qualification ? item.qualification.score : null;
    case "confidence":
      return item.qualification ? item.qualification.confidence : null;
    case "status":
      return item.prospect.status.toLowerCase();
    case "campaign":
      return (item.campaign?.name ?? "").toLowerCase();
    case "research":
      return item.research_date ?? null;
  }
}

/** Nulls always sort last, regardless of direction. */
function compareValues(a: CellValue, b: CellValue): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;

  if (typeof a === "number" && typeof b === "number") return a - b;

  return String(a).localeCompare(String(b));
}

export default function ProspectsPage() {
  const router = useRouter();

  const { data: records, error, loading, reload } = useApi(
    () => api.listProspects({ limit: 500 }),
    [],
  );

  const { data: campaigns } = useApi(() => api.listCampaigns(), []);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [campaignFilter, setCampaignFilter] = useState("ALL");
  const [sort, setSort] = useState<SortState>({ key: "research", dir: "desc" });

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();

    const filtered = (records ?? []).filter((item) => {
      if (statusFilter !== "ALL" && item.prospect.status !== statusFilter) return false;
      if (campaignFilter !== "ALL" && item.prospect.campaign_id !== campaignFilter) return false;
      if (!needle) return true;

      return [
        item.company.name ?? "",
        item.company.domain,
        item.company.industry ?? "",
        item.company.location ?? "",
        item.campaign?.name ?? "",
      ]
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });

    const { dir, key } = sort;

    return [...filtered].sort((a, b) => {
      const av = cellValue(a, key);
      const bv = cellValue(b, key);

      // Keep unqualified records at the bottom in both directions.
      if (av === null || bv === null) {
        if (av === null && bv === null) return a.prospect.id.localeCompare(b.prospect.id);
        return av === null ? 1 : -1;
      }

      const result = compareValues(av, bv);
      if (result !== 0) return dir === "asc" ? result : -result;

      return a.prospect.id.localeCompare(b.prospect.id);
    });
  }, [records, query, statusFilter, campaignFilter, sort]);

  const statusOptions = useMemo(() => {
    const values = new Set((records ?? []).map((item) => item.prospect.status));
    return [...values].sort();
  }, [records]);

  const filtersActive =
    query.trim() !== "" || statusFilter !== "ALL" || campaignFilter !== "ALL";

  function clearFilters() {
    setQuery("");
    setStatusFilter("ALL");
    setCampaignFilter("ALL");
  }

  const total = records?.length ?? 0;

  return (
    <>
      <PageHeader
        action={
          <div className="heading-actions">
            <button
              className="secondary-button"
              disabled={loading}
              onClick={reload}
              type="button"
            >
              {loading ? <span className="spinner" /> : <RefreshCw />}
              Refresh
            </button>

            <Link className="primary-button" href="/discover">
              <Plus />
              Discover prospect
            </Link>
          </div>
        }
        description="Every company researched, scored and qualified against your campaigns."
        title="Prospects"
      />

      <div className="workspace-toolbar">
        <div className="search-box">
          <Search />

          <input
            aria-label="Search prospects"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search company, domain or industry"
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

        <select
          aria-label="Filter by campaign"
          className={`toolbar-select${campaignFilter !== "ALL" ? " filled" : ""}`}
          onChange={(event) => setCampaignFilter(event.target.value)}
          value={campaignFilter}
        >
          <option value="ALL">All campaigns</option>

          {(campaigns ?? []).map((campaign) => (
            <option key={campaign.id} value={campaign.id}>
              {campaign.name}
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
            setSort((current) => ({
              ...current,
              dir: current.dir === "asc" ? "desc" : "asc",
            }))
          }
          type="button"
        >
          <ArrowUpDown />
          {sort.dir === "asc" ? "Ascending" : "Descending"}
        </button>
      </div>

      <div className="table-meta">
        <span>
          <strong>{rows.length}</strong> of {total}{" "}
          {total === 1 ? "prospect" : "prospects"}
        </span>

        <span className="meta-dot" />

        <span>
          Sorted by {SORT_LABEL[sort.key].toLowerCase()} ·{" "}
          {sort.dir === "asc" ? "ascending" : "descending"}
        </span>

        {filtersActive ? <span className="selection-note">Filters active</span> : null}
      </div>

      {error && !records ? (
        <>
          <ErrorNotice message={error} />

          <button className="secondary-button" onClick={reload} type="button">
            Retry
          </button>
        </>
      ) : loading && !records ? (
        <LoadingBlock label="Loading prospects" />
      ) : total === 0 ? (
        <EmptyState title="No prospects yet">
          Run a discovery against a campaign to research the first company.{" "}
          <Link className="evidence-link" href="/discover">
            Go to discovery
          </Link>
          .
        </EmptyState>
      ) : rows.length === 0 ? (
        <EmptyState title="No matches">
          No prospect matches the current search or filters.{" "}
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
                <th className="col-secondary">Industry</th>
                <th className="col-secondary">Campaign</th>
                <th className="col-compact">Qualification</th>
                <th className="col-secondary">Confidence</th>
                <th>Status</th>
                <th className="col-secondary">Last researched</th>
                <th />
              </tr>
            </thead>

            <tbody>
              {rows.map((item) => (
                <tr
                  className="clickable"
                  key={item.prospect.id}
                  onClick={() => router.push(`/prospects/${item.prospect.id}`)}
                >
                  <td>
                    <div className="company-cell">
                      <CompanyLogo
                        domain={item.company.domain}
                        name={item.company.name}
                      />

                      <div>
                        <strong>
                          <Link className="row-link" href={`/prospects/${item.prospect.id}`}>
                            {displayCompany(item.company.name, item.company.domain)}
                          </Link>
                        </strong>

                        <span>{item.company.domain}</span>
                      </div>
                    </div>
                  </td>

                  <td className="col-secondary">
                    <span className="muted-cell clamp-2">
                      {item.company.industry ?? <span className="faint">—</span>}
                    </span>
                  </td>

                  <td className="col-secondary">
                    <span className="campaign-cell">
                      <span className="campaign-dot" />
                      {item.campaign ? item.campaign.name : "—"}
                    </span>
                  </td>

                  <td className="col-compact">
                    {item.qualification ? (
                      <ScoreCell score={item.qualification.score} />
                    ) : (
                      <span className="faint">—</span>
                    )}
                  </td>

                  <td className="col-secondary">
                    {item.qualification ? (
                      <ConfidenceValue value={item.qualification.confidence} />
                    ) : (
                      <span className="faint">—</span>
                    )}
                  </td>

                  <td>
                    <StatusBadge status={item.prospect.status} />
                  </td>

                  <td className="col-secondary">
                    <span
                      className="muted-cell"
                      title={item.research_date ?? undefined}
                    >
                      {formatRelative(item.research_date)}
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

      {error && records ? <ErrorNotice message={error} /> : null}
    </>
  );
}
