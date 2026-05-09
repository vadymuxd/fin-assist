"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";

type State = "idle" | "loading" | "done" | "error";

export default function SyncButton() {
  const [state, setState] = useState<State>("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");

  async function handleSync() {
    setState("loading");
    setErrorMsg("");
    try {
      const res = await fetch("/api/sync", { method: "POST" });
      if (res.ok) {
        setState("done");
      } else {
        const body = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
        setErrorMsg(body?.error ?? `HTTP ${res.status}`);
        setState("error");
      }
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "Network error");
      setState("error");
    }
    setTimeout(() => setState("idle"), 5000);
  }

  const label =
    state === "loading" ? "Syncing…" :
    state === "done"    ? "Synced!"  :
    state === "error"   ? "Failed"   : "Sync";

  const colorClass =
    state === "done"  ? "text-emerald-600 dark:text-emerald-400" :
    state === "error" ? "text-rose-600 dark:text-rose-400" :
    "text-gray-600 dark:text-gray-300";

  return (
    <div className="relative group">
      <button
        onClick={handleSync}
        disabled={state === "loading"}
        title={state === "error" && errorMsg ? errorMsg : undefined}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${colorClass}`}
      >
        <RefreshCw size={13} strokeWidth={2} className={state === "loading" ? "animate-spin" : ""} />
        {label}
      </button>
      {state === "error" && errorMsg && (
        <div className="absolute right-0 top-full mt-1 z-50 w-64 rounded-lg border border-rose-200 dark:border-rose-800 bg-white dark:bg-gray-900 px-3 py-2 text-[11px] text-rose-600 dark:text-rose-400 shadow-lg break-words">
          {errorMsg}
        </div>
      )}
    </div>
  );
}
