"use client";

/* TagBadge - the site-wide pill marker. Same tinted language as the data-flow
   chips: accent at ~8% alpha + hairline border, accent-colored text. Known
   labels get a brand accent automatically; pass `color` for semantic states
   (status pills, Active/Coming soon). Everything else falls back to a quiet
   neutral gray. */

import type { ReactNode } from "react";

const TAG_ACCENTS: Record<string, string> = {
  Azure: "#4493f8",
  Foundry: "#a371f7",
};

export function TagBadge({ label, color, children }: { label: string; color?: string; children?: ReactNode }) {
  const c = color ?? TAG_ACCENTS[label] ?? "#8b949e";
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 4,
      flexShrink: 0,
      whiteSpace: "nowrap",
      padding: "2px 9px",
      borderRadius: "999px",
      fontSize: 11,
      fontWeight: 600,
      lineHeight: "16px",
      color: c,
      backgroundColor: `${c}14`,
      border: `1px solid ${c}4d`,
    }}>{children}{label}</span>
  );
}
