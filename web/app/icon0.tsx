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
          background: "#0A84FF",
        }}
      >
        <div
          style={{
            width: 300,
            height: 300,
            borderRadius: 66,
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            gap: 26,
            paddingBottom: 38,
          }}
        >
          <div style={{ width: 44, height: 126, background: "white", borderRadius: 10 }} />
          <div style={{ width: 44, height: 208, background: "white", borderRadius: 10 }} />
          <div style={{ width: 44, height: 78, background: "white", borderRadius: 10 }} />
        </div>
      </div>
    ),
    { ...size }
  );
}
