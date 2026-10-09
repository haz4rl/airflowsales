"use client";

import { useState } from "react";
import { ErrorNotice, SuccessNotice } from "./ui";
import { api, apiErrorMessage } from "@/lib/api";
import type { WorkflowRun } from "@/lib/types";

interface ApprovalPanelProps {
  onCompleted?: (run: WorkflowRun) => void;
  runId: string;
}

export function ApprovalPanel({ onCompleted, runId }: ApprovalPanelProps) {
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState<null | boolean>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit(approved: boolean) {
    setError(null);
    setDone(null);
    setSubmitting(approved);
    try {
      const run = await api.approveRun(runId, {
        approved,
        note: note.trim() ? note.trim() : null,
      });
      setDone(
        approved
          ? "Approved. The run and prospect are now marked APPROVED."
          : "Rejected. The run and prospect are now marked REJECTED.",
      );
      setNote("");
      onCompleted?.(run);
    } catch (cause) {
      setError(apiErrorMessage(cause));
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <div className="approval-panel">
      <h3>Reviewer decision</h3>
      {error ? <ErrorNotice message={error} /> : null}
      {done ? <SuccessNotice message={done} /> : null}

      <div className="field">
        <label className="field-label" htmlFor="approval-note">
          Reviewer note
        </label>
        <textarea
          className="textarea"
          id="approval-note"
          onChange={(event) => setNote(event.target.value)}
          placeholder="Optional note recorded on the workflow run"
          rows={3}
          value={note}
        />
        <p className="field-hint">Stored as a HUMAN workflow event.</p>
      </div>

      <div className="approval-actions">
        <button
          className="primary-button"
          disabled={submitting !== null}
          onClick={() => void submit(true)}
          type="button"
        >
          {submitting === true ? <span className="spinner" /> : null}
          Approve
        </button>
        <button
          className="secondary-button"
          disabled={submitting !== null}
          onClick={() => void submit(false)}
          type="button"
        >
          {submitting === false ? <span className="spinner" /> : null}
          Reject
        </button>
      </div>
    </div>
  );
}
