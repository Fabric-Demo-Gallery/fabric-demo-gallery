import { Suspense } from "react";
import type { Metadata } from "next";
import DemoDetailClient from "./DemoDetailClient";
import { DEMOS } from "@/lib/demoCatalog";

export function generateStaticParams() {
  return Object.keys(DEMOS).map((id) => ({ id }));
}

// Per-demo title/description so browser tabs, search results, and shared
// links (Teams/Outlook cards) identify the specific demo instead of the
// generic site name.
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const demo = DEMOS[id];
  if (!demo) return {};
  const title = `${demo.title} — ${demo.industry}`;
  const description = demo.description.length > 200 ? `${demo.description.slice(0, 197)}…` : demo.description;
  return {
    title,
    description,
    alternates: { canonical: `/demos/${id}/` },
    openGraph: {
      title: `${title} | Fabric Demo Gallery`,
      description,
      url: `https://www.fabricdemogallery.com/demos/${id}/`,
      siteName: "Fabric Demo Gallery",
      type: "website",
      images: [{ url: "/og-card.png", width: 1200, height: 630, alt: "Fabric Demo Gallery" }],
    },
    twitter: {
      card: "summary_large_image",
      title: `${title} | Fabric Demo Gallery`,
      description,
      images: ["/og-card.png"],
    },
  };
}

export default async function DemoDetailPage({ params }: { params: Promise<{ id: string }> }) {
  await params; // consume params (id used by client component via useParams)
  return (
    <div>
      <Suspense>
        <DemoDetailClient />
      </Suspense>
    </div>
  );
}
