import HomeClient from "./HomeClient";
import { industries } from "@/lib/industryCatalog";

// Server component wrapper: the gallery UI is a client component whose body is
// NOT prerendered into static HTML (it bails out to client rendering), so any
// SEO markup placed inside it never reaches crawlers. JSON-LD must live here.
// ItemList mirrors the visible industry cards — Bing rich results + Copilot.
const HOME_ITEMLIST_LD = {
  "@context": "https://schema.org",
  "@type": "ItemList",
  name: "Microsoft Fabric demos by industry",
  itemListElement: industries
    .filter((i) => i.enabled)
    .map((i, idx) => ({
      "@type": "ListItem",
      position: idx + 1,
      name: i.title,
      url: `https://www.fabricdemogallery.com/industries/${i.slug}/`,
    })),
};

export default function Home() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(HOME_ITEMLIST_LD) }} />
      <HomeClient />
    </>
  );
}
