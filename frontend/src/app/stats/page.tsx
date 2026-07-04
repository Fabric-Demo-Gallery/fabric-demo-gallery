"use client";

import { notFound } from "next/navigation";
import StatsClient from "./StatsClient";

// Build-time flag: the usage dashboard is only exposed on environments built
// with NEXT_PUBLIC_STATS_ENABLED=1 (currently dev). Elsewhere it 404s.
const STATS_ENABLED = process.env.NEXT_PUBLIC_STATS_ENABLED === "1";

export default function StatsPage() {
  if (!STATS_ENABLED) notFound();
  return <StatsClient />;
}
