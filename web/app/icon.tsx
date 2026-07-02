import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
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
          borderRadius: 7,
        }}
      >
        <div
          style={{
            width: 20,
            height: 20,
            borderRadius: 5,
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            gap: 2,
            paddingBottom: 3,
          }}
        >
          <div style={{ width: 3, height: 8, background: "white", borderRadius: 1 }} />
          <div style={{ width: 3, height: 13, background: "white", borderRadius: 1 }} />
          <div style={{ width: 3, height: 5, background: "white", borderRadius: 1 }} />
        </div>
      </div>
    ),
    { ...size }
  );
}
