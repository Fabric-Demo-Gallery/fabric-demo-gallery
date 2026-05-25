// Next.js App Router loading.tsx — shown as Suspense fallback during client-side navigation.
// Uses pure CSS so it renders correctly without FluentProvider context.
export default function Loading() {
  return (
    <>
      <style>{`
        @keyframes fabric-spin {
          to { transform: rotate(360deg); }
        }
        .fabric-spinner {
          width: 32px;
          height: 32px;
          border: 3px solid #30363d;
          border-top-color: #3fb68b;
          border-radius: 50%;
          animation: fabric-spin 0.75s linear infinite;
        }
      `}</style>
      <div style={{
        width: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        paddingTop: "48px",
        gap: "12px",
      }}>
        <div className="fabric-spinner" />
        <span style={{ color: "#8b949e", fontSize: "13px", fontFamily: "'Segoe UI', sans-serif" }}>
          Loading…
        </span>
      </div>
    </>
  );
}
