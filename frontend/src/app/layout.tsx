import type { Metadata } from "next";
import "./globals.css";
import ClientShell from "./ClientShell";

export const metadata: Metadata = {
  metadataBase: new URL("https://fabricdemogallery.com"),
  title: "Fabric Demo Gallery",
  description:
    "One-click deployable industry demos for Microsoft Fabric",
  openGraph: {
    title: "Fabric Demo Gallery",
    description: "One-click deployable industry demos for Microsoft Fabric",
    url: "https://fabricdemogallery.com",
    siteName: "Fabric Demo Gallery",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Fabric Demo Gallery",
    description: "One-click deployable industry demos for Microsoft Fabric",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{
        minHeight: "100vh",
        margin: 0,
        fontFamily: "'Segoe UI Variable Text', 'Segoe UI Variable', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif",
        backgroundColor: "#0d1117",
        WebkitFontSmoothing: "antialiased",
      }}>
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}
