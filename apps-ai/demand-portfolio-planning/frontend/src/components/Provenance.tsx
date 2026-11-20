import type { Kind } from "../types";
import { useT } from "../I18nProvider";
import type { Key } from "../i18n";

const KIND_KEY: Record<Kind, Key> = {
  fact: "kind.fact",
  assumption: "kind.assumption",
  open_question: "kind.open_question",
  generated: "kind.generated",
  unknown: "kind.unknown",
};

const KINDS: Kind[] = ["fact", "assumption", "open_question", "generated", "unknown"];

export function ProvenanceBadge({ kind }: { kind: Kind }) {
  const t = useT();
  return <span className={`pill pill-${kind}`}>{t(KIND_KEY[kind])}</span>;
}

export function KindDot({ kind }: { kind: Kind }) {
  return <span className={`dot dot-${kind}`} aria-hidden="true" />;
}

export function Legend() {
  const t = useT();
  return (
    <div className="legend">
      <span className="legend-title">{t("legend.title")}</span>
      <div className="legend-items">
        {KINDS.map((k) => (
          <span className="legend-item" key={k}>
            <KindDot kind={k} />
            {t(KIND_KEY[k])}
          </span>
        ))}
      </div>
    </div>
  );
}
