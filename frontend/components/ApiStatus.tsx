"use client";

import { useEffect, useState } from "react";
import { api, apiErrorMessage } from "@/lib/api";

type State = "checking" | "online" | "offline";

export function ApiStatus() {
  const [state, setState] = useState<State>("checking");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        await api.health();
        if (!cancelled) {
          setState("online");
          setMessage("API connected");
        }
      } catch (error) {
        if (!cancelled) {
          setState("offline");
          setMessage(apiErrorMessage(error));
        }
      }
    }

    check();
    const id = window.setInterval(check, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const dotClass =
    state === "online" ? "dot dot-ok" : state === "offline" ? "dot dot-bad" : "dot dot-warn";

  return (
    <span className="chip" title={message || "Checking API health"}>
      <span className={dotClass} />
      {state === "checking"
        ? "Checking API"
        : state === "online"
          ? "API online"
          : "API offline"}
    </span>
  );
}
