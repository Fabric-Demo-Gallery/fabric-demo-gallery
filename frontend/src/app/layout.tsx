import type { Metadata, Viewport } from "next";
import "./globals.css";
import ClientShell from "./ClientShell";

export const metadata: Metadata = {
  metadataBase: new URL("https://www.fabricdemogallery.com"),
  title: {
    default: "Fabric Demo Gallery",
    template: "%s | Fabric Demo Gallery",
  },
  // ~160 chars — a description this rich makes Bing/Google use it as the
  // search snippet instead of scraping the first DOM text (which was the
  // admin-consent banner).
  description:
    "Browse production-ready Microsoft Fabric demos by industry and deploy to your tenant in one click — lakehouses, real-time intelligence, AI agents and Power BI.",
  manifest: "/site.webmanifest",
  // Canonical host: the same build is served on 5 hostnames (apex, www, the
  // SWA default hostname, preview, dev) — without a canonical, search engines
  // treat them as duplicates and can split ranking signals or index the wrong
  // host. metadataBase + relative canonical makes every page point at www.
  alternates: { canonical: "/" },
  icons: {
    icon: "/pwa-192.png",
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "Fabric Demo Gallery",
    description:
      "Browse production-ready Microsoft Fabric demos by industry and deploy to your tenant in one click — lakehouses, real-time intelligence, AI agents and Power BI.",
    url: "https://www.fabricdemogallery.com",
    siteName: "Fabric Demo Gallery",
    type: "website",
    images: [{ url: "/og-card.png", width: 1200, height: 630, alt: "Fabric Demo Gallery" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Fabric Demo Gallery",
    description:
      "Browse production-ready Microsoft Fabric demos by industry and deploy to your tenant in one click — lakehouses, real-time intelligence, AI agents and Power BI.",
    images: ["/og-card.png"],
  },
};

export const viewport: Viewport = {
  themeColor: "#0d1117",
};

// Structured data — helps Bing (Edge) and Google show rich results.
const JSON_LD = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: "Fabric Demo Gallery",
  url: "https://www.fabricdemogallery.com",
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Web",
  description:
    "One-click deployable industry demos for Microsoft Fabric — lakehouses, notebooks, real-time intelligence, AI agents and Power BI reports across 12 industries.",
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
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
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}
