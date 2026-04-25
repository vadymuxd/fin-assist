"use client";

import { useState } from "react";

const PALETTE = [
  "#2563eb", "#10b981", "#f59e0b", "#8b5cf6",
  "#f43f5e", "#06b6d4", "#6366f1", "#d946ef",
  "#14b8a6", "#f97316", "#84cc16", "#0ea5e9",
];

function colorFor(ticker: string): string {
  let h = 0;
  for (const c of ticker) h = (h * 31 + c.charCodeAt(0)) | 0;
  return PALETTE[Math.abs(h) % PALETTE.length];
}

export default function TickerLogo({ ticker, size = 28 }: { ticker: string; size?: number }) {
  const [err, setErr] = useState(false);
  // Strip trailing dot (BA.) for the logo lookup only
  const base = ticker.replace(/\.$/, "");
  const src = `https://financialmodelingprep.com/image-stock/${base}.png`;
  const fontSize = Math.round(size * 0.36);

  if (err) {
    return (
      <span
        aria-hidden
        style={{
          width: size,
          height: size,
          background: colorFor(ticker),
          borderRadius: "50%",
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize,
          color: "#fff",
          fontWeight: 700,
          flexShrink: 0,
          letterSpacing: "-0.5px",
          userSelect: "none",
        }}
      >
        {base.slice(0, 2)}
      </span>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      onError={() => setErr(true)}
      style={{ borderRadius: "50%", flexShrink: 0, objectFit: "contain" }}
    />
  );
}
