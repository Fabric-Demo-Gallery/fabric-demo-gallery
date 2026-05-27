import { Suspense } from "react";
import DemoDetailClient from "./DemoDetailClient";

export function generateStaticParams() {
  return [
    { id: "manufacturing-qc" },
    { id: "retail-sales" },
    { id: "energy-grid" },
  ];
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
