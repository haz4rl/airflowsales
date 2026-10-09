"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ChevronRight, Globe2, Play, Workflow } from "lucide-react";
import {
  CompanyLogo,
  ConfidenceValue,
  DecisionBadge,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  StatusBadge,
} from "@/components/ui";
import { api, apiErrorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import {
  displayCompany,
  formatRelative,
  isValidDomain,
  normalizeDomain,
} from "@/lib/format";
import type { DiscoveryResponse } from "@/lib/types";

/** Agents the backend runs, in the order they execute. */
const STAGES = [
  { name: "Company search", detail: "Looks up the company record for the domain." },
  { name: "Research agent", detail: "Synthesizes public evidence into company intelligence." },
  { name: "Qualification agent", detail: "Scores the account against the campaign criteria." },
  { name: "Outreach agent", detail: "Drafts a first-touch message grounded in the research." },
  { name: "Critic agent", detail: "Checks every claim against the collected evidence." },
];

export default function DiscoverPage() {
  const {
    data: campaigns,
    error: campaignsError,
    loading: campaignsLoading,
  } = useApi(() => api.listCampaigns(), []);
  const recentQuery = useApi(() => api.listProspects({ limit: 5 }), []);

  const [campaignId, setCampaignId] = useState("");
  const [domain, setDomain] = useState("");
  const [domainError, setDomainError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<DiscoveryResponse | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef<number>(0);

  // ?campaign=<id> is used by the campaigns page; read it after mount so the
  // route can still be statically prerendered without a Suspense boundary.
  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("campaign");
    if (!requested) return;
    setCampaignId((current) => (current ? current : requested));
  }, []);

  // A deep-linked campaign id that no longer exists must not silently point
  // the form at a campaign the API will reject.
  useEffect(() => {
    if (!campaigns || !campaignId) return;
    if (!campaigns.some((campaign) => campaign.id === campaignId)) {
      setCampaignId("");
      setRunError("The requested campaign is no longer available. Select one below.");
    }
  }, [campaigns, campaignId]);

  useEffect(() => {
    if (!campaignId && campaigns && campaigns.length > 0) setCampaignId(campaigns[0].id);
  }, [campaigns, campaignId]);

  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => {
      setElapsed(Math.round((Date.now() - startedAt.current) / 1000));
    }, 1000);
    return () => window.clearInterval(id);
  }, [running]);

  const selectedCampaign = useMemo(
    () => campaigns?.find((campaign) => campaign.id === campaignId) ?? null,
    [campaigns, campaignId],
  );

  const domainReady = isValidDomain(domain);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRunError(null);
    setResult(null);

    if (!campaignId || !campaigns?.some((campaign) => campaign.id === campaignId)) {
      setRunError("Select a valid campaign first.");
      return;
    }
    if (!domainReady) {
      setDomainError("Domain must look like company.com");
      return;
    }
    setDomainError(null);

    setRunning(true);
    setElapsed(0);
    startedAt.current = Date.now();
    try {
      const response = await api.discover({
        campaign_id: campaignId,
        domain: normalizeDomain(domain),
      });
      setResult(response);
      recentQuery.reload();
    } catch (cause) {
      setRunError(apiErrorMessage(cause));
    } finally {
      setRunning(false);
    }
  }

  if (campaignsLoading && !campaigns) return <LoadingBlock label="Loading campaigns" />;

  return (
    <>
      <PageHeader
        action={
          <Link className="secondary-button" href="/campaigns">
            Manage campaigns
          </Link>
        }
        description="Research a single company against a campaign: evidence, a qualification score and a first-touch draft."
        title="Discover"
      />

      {campaignsError ? <ErrorNotice message={campaignsError} /> : null}

      {campaigns && campaigns.length === 0 ? (
        <EmptyState title="No campaigns available">
          Discovery is evaluated against a campaign.{" "}
          <Link className="evidence-link" href="/campaigns">
            Create one first
          </Link>
          .
        </EmptyState>
      ) : (
        <div className="discover-layout">
          <section>
            <form className="discover-form" onSubmit={submit}>
              {runError ? <ErrorNotice message={runError} /> : null}

              <div className="form-step">
                <span>01</span>
                <div>
                  <label htmlFor="discover-campaign">Choose a campaign</label>
                  <p>The company is scored against this campaign&apos;s criteria.</p>
                  <select
                    aria-describedby={selectedCampaign ? "discover-campaign-hint" : undefined}
                    aria-label="Campaign"
                    id="discover-campaign"
                    onChange={(event) => setCampaignId(event.target.value)}
                    required
                    value={campaignId}
                  >
                    <option disabled value="">
                      Select a campaign
                    </option>
                    {(campaigns ?? []).map((campaign) => (
                      <option key={campaign.id} value={campaign.id}>
                        {campaign.name}
                      </option>
                    ))}
                  </select>
                  {selectedCampaign ? (
                    <p className="field-hint" id="discover-campaign-hint">
                      {selectedCampaign.qualification_criteria}
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="form-step">
                <span>02</span>
                <div>
                  <label htmlFor="discover-domain">Enter a company domain</label>
                  <p>Public signals are gathered and saved as an intelligence record.</p>
                  <div className="domain-input">
                    <Globe2 />
                    <input
                      aria-describedby="discover-domain-hint"
                      aria-invalid={domainError ? true : undefined}
                      autoComplete="off"
                      id="discover-domain"
                      onChange={(event) => {
                        setDomain(event.target.value);
                        if (domainError) setDomainError(null);
                      }}
                      placeholder="company.com"
                      spellCheck={false}
                      value={domain}
                    />
                  </div>
                  <p className={`field-hint${domainError ? " field-error" : ""}`} id="discover-domain-hint">
                    {domainError ?? "Enter a domain such as company.com."}
                  </p>
                </div>
              </div>

              {running ? (
                <div
                  aria-label="Discovery in progress"
                  className="progress"
                  role="progressbar"
                >
                  <span />
                </div>
              ) : (
                <button
                  className="primary-button discover-button"
                  disabled={domain.trim() === "" || !campaignId}
                  type="submit"
                >
                  <Play />
                  Run discovery
                </button>
              )}

              {running ? (
                <p className="progress-note">
                  <span className="spinner" />
                  Researching {normalizeDomain(domain)} · {elapsed}s elapsed.
                </p>
              ) : null}
            </form>

            {result ? (
              <div className="panel fade-in" style={{ marginTop: 24 }}>
                <div className="detail-head" style={{ paddingTop: 4 }}>
                  <CompanyLogo
                    domain={result.company.domain}
                    eager
                    name={result.company.name}
                  />

                  <div className="detail-identity">
                    <div className="eyebrow">
                      {selectedCampaign ? <span>{selectedCampaign.name}</span> : null}
                      <StatusBadge status={result.prospect.status} />
                      {result.qualification ? (
                        <DecisionBadge decision={result.qualification.decision} />
                      ) : null}
                    </div>
                    <h2>{displayCompany(result.company.name, result.company.domain)}</h2>
                    <p className="mono">{result.company.domain}</p>
                  </div>
                </div>

                <div className="runs-summary">
                  <div>
                    <span className="summary-label">Score</span>
                    <strong>{result.qualification ? result.qualification.score : "—"}</strong>
                    <span className="summary-note">of 100</span>
                  </div>
                  <div>
                    <span className="summary-label">Confidence</span>
                    <ConfidenceValue value={result.qualification?.confidence ?? null} />
                    <span className="summary-note">agent estimate</span>
                  </div>
                  <div>
                    <span className="summary-label">Evidence</span>
                    <strong>{result.evidence.length}</strong>
                    <span className="summary-note">
                      {result.evidence.length === 1 ? "source" : "sources"}
                    </span>
                  </div>
                </div>

                {result.company.description ? (
                  <p className="tiny faint" style={{ lineHeight: 1.6 }}>
                    {result.company.description}
                  </p>
                ) : null}

                <div className="heading-actions" style={{ marginTop: 18 }}>
                  <Link className="primary-button" href={`/prospects/${result.prospect.id}`}>
                    Open prospect
                  </Link>
                  {result.workflow_run_id ? (
                    <Link className="secondary-button" href={`/runs/${result.workflow_run_id}`}>
                      <Workflow />
                      View workflow run
                    </Link>
                  ) : null}
                  <button
                    className="secondary-button"
                    onClick={() => {
                      setResult(null);
                      setDomain("");
                    }}
                    type="button"
                  >
                    Discover another
                  </button>
                </div>
              </div>
            ) : null}
          </section>

          <aside className="discover-preview">
            <div className="preview-label">Agents in this run</div>
            {STAGES.map((stage, index) => (
              <div className="preview-step" key={stage.name}>
                <span>{index + 1}</span>
                <div>
                  <strong>{stage.name}</strong>
                  <p>{stage.detail}</p>
                </div>
              </div>
            ))}
          </aside>
        </div>
      )}

      <div className="panel" style={{ marginTop: 26 }}>
        <div className="section-title">
          <div>
            <h2>Recent discoveries</h2>
            <p>Newest research runs first.</p>
          </div>

          <Link className="secondary-button" href="/prospects">
            View all
            <ChevronRight />
          </Link>
        </div>

        {recentQuery.loading ? (
          <LoadingBlock label="Loading" />
        ) : recentQuery.error ? (
          <ErrorNotice message={recentQuery.error} />
        ) : (recentQuery.data ?? []).length === 0 ? (
          <EmptyState title="Nothing discovered yet">
            Results appear here as soon as a run completes.
          </EmptyState>
        ) : (
          <div className="recent-list">
            {(recentQuery.data ?? []).map((item) => (
              <Link className="recent-row" href={`/prospects/${item.prospect.id}`} key={item.prospect.id}>
                <CompanyLogo domain={item.company.domain} name={item.company.name} />

                <div className="recent-body">
                  <strong className="recent-title">
                    {displayCompany(item.company.name, item.company.domain)}
                  </strong>
                  <span className="recent-meta">
                    {item.company.domain}
                    {item.campaign ? ` · ${item.campaign.name}` : ""}
                    {item.research_date ? ` · ${formatRelative(item.research_date)}` : ""}
                  </span>
                </div>

                {item.qualification ? (
                  <span className="recent-score">
                    <strong>{item.qualification.score}</strong>
                    <span>score</span>
                  </span>
                ) : null}

                <StatusBadge status={item.prospect.status} />

                <ChevronRight className="table-arrow" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
