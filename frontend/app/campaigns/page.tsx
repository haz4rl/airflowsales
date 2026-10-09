"use client";

import type { FormEvent } from "react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Plus, Trash2, X } from "lucide-react";
import {
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeader,
  SuccessNotice,
} from "@/components/ui";
import { api, apiErrorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { formatRelative, humanizeKey, stringifyValue } from "@/lib/format";
import type { Campaign } from "@/lib/types";

/** Free-text "key: value" lines → the dict the API already expects. */
function parseCharacteristics(text: string): Record<string, unknown> | null {
  const parsed: Record<string, unknown> = {};

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;

    const separator = line.indexOf(":");
    if (separator === -1) return null;

    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();
    if (!key || !value) return null;

    const asNumber = Number(value);
    parsed[key] = value !== "" && !Number.isNaN(asNumber) && String(asNumber) === value ? asNumber : value;
  }

  return parsed;
}

export default function CampaignsPage() {
  const { data: campaigns, error, loading, reload } = useApi(() => api.listCampaigns(), []);
  const { data: prospects } = useApi(() => api.listProspects({ limit: 500 }), []);

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [product, setProduct] = useState("");
  const [industries, setIndustries] = useState("");
  const [characteristics, setCharacteristics] = useState("");
  const [criteria, setCriteria] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Campaign | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function prospectCount(campaignId: string): number {
    return (prospects ?? []).filter((item) => item.prospect.campaign_id === campaignId).length;
  }

  function openDeleteDialog(campaign: Campaign) {
    setDeleteTarget(campaign);
    setDeleteError(null);
  }

  function closeDeleteDialog() {
    if (deleting) return;
    setDeleteTarget(null);
    setDeleteError(null);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteCampaign(deleteTarget.id);
      setSaved(`Campaign “${deleteTarget.name}” deleted.`);
      setDeleteTarget(null);
      reload();
    } catch (cause) {
      setDeleteError(apiErrorMessage(cause));
    } finally {
      setDeleting(false);
    }
  }

  useEffect(() => {
    if (!deleteTarget) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") closeDeleteDialog();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deleteTarget, deleting]);

  function closeForm() {
    setShowForm(false);
    setFormError(null);
    setName("");
    setProduct("");
    setIndustries("");
    setCharacteristics("");
    setCriteria("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const parsed = parseCharacteristics(characteristics);
    if (parsed === null) {
      setFormError("Target characteristics must be one key: value pair per line.");
      return;
    }

    setSubmitting(true);
    try {
      const campaign = await api.createCampaign({
        name: name.trim(),
        product_description: product.trim(),
        target_industries: industries
          .split(",")
          .map((entry) => entry.trim())
          .filter(Boolean),
        target_company_characteristics: parsed,
        qualification_criteria: criteria.trim(),
      });
      setSaved(`Campaign “${campaign.name}” created.`);
      closeForm();
      reload();
    } catch (cause) {
      setFormError(apiErrorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader
        action={
          showForm ? (
            <button className="secondary-button" onClick={closeForm} type="button">
              <X />
              Close
            </button>
          ) : (
            <button className="primary-button" onClick={() => setShowForm(true)} type="button">
              <Plus />
              New campaign
            </button>
          )
        }
        description="Each campaign defines the product, target market and qualification criteria the agents score companies against."
        title="Campaigns"
      />

      {saved ? <SuccessNotice message={saved} /> : null}

      {showForm ? (
        <div className="panel fade-in" style={{ marginBottom: 24 }}>
          <div className="section-title">
            <div>
              <h2>New campaign</h2>
              <p>Discovery runs against one campaign at a time.</p>
            </div>
          </div>

          <form onSubmit={submit}>
            {formError ? <ErrorNotice message={formError} /> : null}

            <div className="field-row">
              <div className="field">
                <label className="field-label" htmlFor="campaign-name">
                  Name
                </label>
                <input
                  className="input"
                  id="campaign-name"
                  onChange={(event) => setName(event.target.value)}
                  placeholder="European B2B SaaS"
                  required
                  value={name}
                />
              </div>

              <div className="field">
                <label className="field-label" htmlFor="campaign-industries">
                  Target industries
                </label>
                <input
                  className="input"
                  id="campaign-industries"
                  onChange={(event) => setIndustries(event.target.value)}
                  placeholder="SaaS, FinTech, Logistics"
                  value={industries}
                />
                <p className="field-hint">Comma separated.</p>
              </div>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="campaign-product">
                What you sell
              </label>
              <textarea
                className="textarea"
                id="campaign-product"
                onChange={(event) => setProduct(event.target.value)}
                placeholder="AI sales intelligence for revenue teams"
                required
                value={product}
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="campaign-criteria">
                Qualification criteria
              </label>
              <textarea
                className="textarea"
                id="campaign-criteria"
                onChange={(event) => setCriteria(event.target.value)}
                placeholder="Growing B2B software company with an active commercial team of at least five people"
                required
                rows={3}
                value={criteria}
              />
              <p className="field-hint">
                The qualification agent scores every researched company against this text.
              </p>
            </div>

            <div className="field">
              <label className="field-label" htmlFor="campaign-chars">
                Target characteristics
              </label>
              <textarea
                className="textarea"
                id="campaign-chars"
                onChange={(event) => setCharacteristics(event.target.value)}
                placeholder={"region: Europe\nmin_headcount: 50"}
                rows={3}
                value={characteristics}
              />
              <p className="field-hint">Optional. One key: value pair per line.</p>
            </div>

            <div className="heading-actions">
              <button className="primary-button" disabled={submitting} type="submit">
                {submitting ? <span className="spinner" /> : <Plus />}
                {submitting ? "Creating…" : "Create campaign"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {error ? (
        <>
          <ErrorNotice message={error} />
          <button className="secondary-button" onClick={reload} type="button">
            Retry
          </button>
        </>
      ) : loading ? (
        <LoadingBlock label="Loading campaigns" />
      ) : !campaigns || campaigns.length === 0 ? (
        <EmptyState title="No campaigns yet">
          {showForm
            ? "Create the first campaign with the form above."
            : "Create a campaign to define the market you are selling into, then run discovery against it."}
        </EmptyState>
      ) : (
        <div className="campaign-list">
          {campaigns.map((campaign) => (
            <article className="campaign-card" key={campaign.id}>
              <div className="campaign-head">
                <div style={{ minWidth: 0 }}>
                  <h2>{campaign.name}</h2>
                  <span className="campaign-sub">Created {formatRelative(campaign.created_at)}</span>
                </div>

                <div className="campaign-stats">
                  <div>
                    <strong>{prospectCount(campaign.id)}</strong>
                    <span>prospects</span>
                  </div>
                  <div>
                    <strong>{campaign.target_industries.length}</strong>
                    <span>industries</span>
                  </div>
                </div>
              </div>

              <p className="campaign-criteria">{campaign.qualification_criteria}</p>

              <div className="evidence-meta">
                {campaign.target_industries.length === 0 ? (
                  <span className="tiny faint">No target industries specified.</span>
                ) : (
                  campaign.target_industries.map((industry) => (
                    <span className="chip" key={industry}>
                      {industry}
                    </span>
                  ))
                )}
              </div>

              <dl className="kv">
                <dt>Selling</dt>
                <dd>{campaign.product_description}</dd>
              </dl>

              <div className="campaign-chars">
                <h3 className="chars-label">Characteristics</h3>
                {Object.keys(campaign.target_company_characteristics).length === 0 ? (
                  <span className="value-none">Not specified</span>
                ) : (
                  <dl className="chars-list">
                    {Object.entries(campaign.target_company_characteristics).map(
                      ([key, value]) => (
                        <div className="char-row" key={key}>
                          <dt>{humanizeKey(key)}</dt>
                          <dd>{stringifyValue(value)}</dd>
                        </div>
                      ),
                    )}
                  </dl>
                )}
              </div>

              <div className="campaign-foot">
                <button
                  className="secondary-button"
                  onClick={() => openDeleteDialog(campaign)}
                  type="button"
                >
                  <Trash2 />
                  Delete
                </button>

                <Link className="secondary-button" href={`/discover?campaign=${campaign.id}`}>
                  Use in discovery
                </Link>
              </div>
            </article>
          ))}
        </div>
      )}

      {deleteTarget ? (
        <div
          className="dialog-overlay"
          onClick={closeDeleteDialog}
          role="presentation"
        >
          <div
            aria-labelledby="delete-campaign-title"
            aria-modal="true"
            className="dialog fade-in"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <h2 id="delete-campaign-title">
              Delete “{deleteTarget.name}”?
            </h2>

            {prospectCount(deleteTarget.id) > 0 ? (
              <>
                <p>
                  This campaign has research history attached to it. Airflow Sales
                  never deletes prospect, qualification or workflow data, so a
                  campaign with history cannot be removed. Create a new campaign
                  instead if you need different criteria.
                </p>

                <div className="dialog-facts">
                  <span>
                    <strong>{prospectCount(deleteTarget.id)}</strong>{" "}
                    {prospectCount(deleteTarget.id) === 1 ? "prospect" : "prospects"} researched
                    under this campaign
                  </span>
                  <span>
                    Their qualifications, evidence and workflow runs stay available
                    on the prospect and run pages.
                  </span>
                </div>

                <div className="dialog-actions">
                  <button className="secondary-button" onClick={closeDeleteDialog} type="button">
                    Close
                  </button>
                </div>
              </>
            ) : (
              <>
                <p>
                  This campaign has no prospects or workflow history. Deleting it
                  removes only the campaign definition — its criteria, target
                  industries and characteristics. This cannot be undone.
                </p>

                {deleteError ? <ErrorNotice message={deleteError} /> : null}

                <div className="dialog-actions">
                  <button className="secondary-button" onClick={closeDeleteDialog} type="button">
                    Cancel
                  </button>
                  <button
                    className="danger-button"
                    disabled={deleting}
                    onClick={() => void confirmDelete()}
                    type="button"
                  >
                    {deleting ? <span className="spinner" /> : <Trash2 />}
                    {deleting ? "Deleting…" : "Delete campaign"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
