import Link from "next/link";

// App Router 404 page. In static export this is emitted as 404.html, so invalid
// industry/demo slugs get a branded page instead of a blank/raw Next default.
export default function NotFound() {
  return (
    <div
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
      <div style={{ fontSize: "56px", fontWeight: 700, color: "#3fb68b", lineHeight: 1 }}>404</div>
      <h1 style={{ fontSize: "22px", fontWeight: 600, color: "#e6edf3", margin: 0 }}>Page not found</h1>
      <p style={{ fontSize: "14px", color: "#8b949e", maxWidth: "440px", margin: "0 0 8px" }}>
        The page you&rsquo;re looking for doesn&rsquo;t exist or may have moved. Pick an industry from the gallery to get
        started.
      </p>
      <Link
        href="/"
        style={{
          display: "inline-block",
          padding: "8px 18px",
          borderRadius: "6px",
          backgroundColor: "#238636",
          color: "#fff",
          fontSize: "14px",
          fontWeight: 600,
          textDecoration: "none",
        }}
      >
        Back to the gallery
      </Link>
    </div>
  );
}
