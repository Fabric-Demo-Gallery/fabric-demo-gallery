import { Suspense } from "react";
import DemoDetailClient from "./DemoDetailClient";
import { DEMOS } from "@/lib/demoCatalog";

export function generateStaticParams() {
  return Object.keys(DEMOS).map((id) => ({ id }));
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
