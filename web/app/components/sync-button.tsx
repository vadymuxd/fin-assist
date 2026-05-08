"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";

type State = "idle" | "loading" | "done" | "error";

export default function SyncButton() {
  const [state, setState] = useState<State>("idle");

  async function handleSync() {
    setState("loading");
    try {
      const res = await fetch("/api/sync", { method: "POST" });
      setState(res.ok ? "done" : "error");
    } catch {
      setState("error");
    }
    setTimeout(() => setState("idle"), 3000);
  }

  const label =
    state === "loading" ? "Syncing…" :
    state === "done"    ? "Synced!"  :
    state === "error"   ? "Failed"   : "Sync";

  return (
    <button
      onClick={handleSync}
      disabled={state === "loading"}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <RefreshCw size={13} strokeWidth={2} className={state === "loading" ? "animate-spin" : ""} />
      {label}
    </button>
  );
}
