import { ImageResponse } from "next/og";

// 512x512 maskable icon for Android PWA install / home screen.
// Symbol sized to fit within Android's ~80% safe zone after masking.
export const size = { width: 512, height: 512 };
export const contentType = "image/png";

export default function Icon0() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(135deg, #2563eb 0%, #6366f1 100%)",
        }}
      >
        <svg
          width="280"
          height="280"
          viewBox="0 0 24 24"
          fill="none"
          stroke="white"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 17l6-6 4 4 8-8" />
          <path d="M14 7h7v7" />
        </svg>
      </div>
    ),
    { ...size }
  );
}
