"use client";

import Link from "next/link";
import { useEffect } from "react";

// App Router error boundary. Catches render/runtime errors on any route and shows
// a branded recovery screen with retry + a way back, instead of a blank page.
// Pure inline styles so it renders even if FluentProvider context is unavailable.
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface the real error in the console for diagnostics.
    console.error(error);
  }, [error]);

  return (
    <div
      role="alert"
      style={{
        width: "100%",
        minHeight: "60vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: "96px 24px",
        gap: "12px",
      }}
    >
      <svg width="44" height="44" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 3 2.5 20.5h19L12 3Z"
          fill="none"
          stroke="#e3b341"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <path d="M12 9.5v4.5" stroke="#e3b341" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="12" cy="17" r="1" fill="#e3b341" />
      </svg>
      <h1 style={{ fontSize: "22px", fontWeight: 600, color: "#e6edf3", margin: 0 }}>Something went wrong</h1>
      <p style={{ fontSize: "14px", color: "#8b949e", maxWidth: "440px", margin: "0 0 8px" }}>
        An unexpected error occurred while loading this page. You can try again, or head back to the gallery.
      </p>
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", justifyContent: "center" }}>
        <button
          onClick={reset}
          style={{
            padding: "8px 18px",
            borderRadius: "6px",
            backgroundColor: "#238636",
            color: "#fff",
            fontSize: "14px",
            fontWeight: 600,
            border: "none",
            cursor: "pointer",
          }}
        >
          Try again
        </button>
        <Link
          href="/"
          style={{
            padding: "8px 18px",
            borderRadius: "6px",
            backgroundColor: "transparent",
            color: "#e6edf3",
            fontSize: "14px",
            fontWeight: 600,
            textDecoration: "none",
            border: "1px solid #30363d",
          }}
        >
          Back to the gallery
        </Link>
      </div>
    </div>
  );
}
