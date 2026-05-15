"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";

type State = "idle" | "loading" | "done" | "error";

export default function GetInsightsButton() {
  const [state, setState] = useState<State>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleClick() {
    setState("loading");
    setErrorMsg("");
    try {
      const res = await fetch("/api/insights", { method: "POST" });
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
    setTimeout(() => setState("idle"), 10000);
  }

  const label =
    state === "loading" ? "Requesting…" :
    state === "done"    ? "Running — refresh in ~2 min" :
    state === "error"   ? "Failed — retry" : "Get Insights";

  const colorClass =
    state === "done"  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" :
    state === "error" ? "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300" :
    "bg-blue-600 text-white hover:bg-blue-700";

  return (
    <div className="relative shrink-0">
      <button
        onClick={handleClick}
        disabled={state === "loading" || state === "done"}
        className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-sm font-medium cursor-pointer transition-colors disabled:cursor-not-allowed disabled:opacity-80 ${colorClass}`}
      >
        <Sparkles size={15} strokeWidth={2} className={state === "loading" ? "animate-pulse" : ""} />
        {label}
      </button>
      {state === "error" && errorMsg && (
        <div className="absolute right-0 top-full mt-1 z-50 w-72 rounded-lg border border-rose-200 dark:border-rose-800 bg-white dark:bg-gray-900 px-3 py-2 text-[11px] text-rose-600 dark:text-rose-400 shadow-lg break-words">
          {errorMsg}
        </div>
      )}
    </div>
  );
}
