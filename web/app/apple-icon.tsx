import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
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
          borderRadius: 40,
        }}
      >
        <div
          style={{
            width: 112,
            height: 112,
            borderRadius: 25,
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            gap: 10,
            paddingBottom: 14,
          }}
        >
          <div style={{ width: 16, height: 45, background: "white", borderRadius: 4 }} />
          <div style={{ width: 16, height: 74, background: "white", borderRadius: 4 }} />
          <div style={{ width: 16, height: 28, background: "white", borderRadius: 4 }} />
        </div>
      </div>
    ),
    { ...size }
  );
}
