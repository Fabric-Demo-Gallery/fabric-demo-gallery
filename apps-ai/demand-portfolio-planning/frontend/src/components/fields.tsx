import { useState } from "react";
import type { TrackedField, TrackedItem } from "../types";
import { ProvenanceBadge } from "./Provenance";
import { useT } from "../I18nProvider";
import type { Key } from "../i18n";

// Demand-record scalar field identifiers. Agents sometimes emit these raw JSON
// keys as item text (e.g. in missing_information); map them to localized labels
// so the UI never shows snake_case identifiers. Free-text items never collide
// with these exact keys, so the mapping is safe to apply everywhere.
const FIELD_KEYS = new Set<string>([
  "demand_title",
  "business_requester",
  "process_owner",
  "business_demand",
  "pain_point",
  "portfolio_area",
  "enterprise_architecture_context",
  "workload_impact",
  "resource_needs",
  "timeline",
]);

function localizeItem(value: string, t: (k: Key) => string): string {
  const key = value.trim();
  return FIELD_KEYS.has(key) ? t(`field.${key}` as Key) : value;
}

export function FieldRow({
  label,
  field,
  onEdit,
}: {
  label: string;
  field: TrackedField;
  onEdit?: (value: string) => void;
}) {
  const t = useT();
  const empty = !field.value || !field.value.trim();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(field.value ?? "");

  const start = () => {
    setDraft(field.value ?? "");
    setEditing(true);
  };
  const save = () => {
    onEdit?.(draft.trim());
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="field-row field-row-editing">
        <span className="field-label">{label}</span>
        <input
          className="field-edit-input"
          value={draft}
          autoFocus
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
            if (e.key === "Escape") setEditing(false);
          }}
        />
        <span className="field-edit-actions">
          <button type="button" className="field-edit-save" onClick={save}>
            {t("edit.save")}
          </button>
          <button type="button" className="field-edit-cancel" onClick={() => setEditing(false)}>
            {t("edit.cancel")}
          </button>
        </span>
      </div>
    );
  }

  return (
    <div className="field-row">
      <span className="field-label">{label}</span>
      <span className={`field-value${empty ? " field-empty" : ""}`}>
        {empty ? t("kind.unknown") : field.value}
      </span>
      {onEdit && (
        <button type="button" className="field-edit-btn" onClick={start} title={t("edit.title")}>
          ✎
        </button>
      )}
      <ProvenanceBadge kind={field.kind} />
    </div>
  );
}

export function ItemList({ items }: { items: TrackedItem[] }) {
  const t = useT();
  if (!items.length) return null;
  return (
    <ul className="item-list">
      {items.map((it, i) => (
        <li key={i} className="item-row">
          <ProvenanceBadge kind={it.kind} />
          <span>{localizeItem(it.value, t)}</span>
        </li>
      ))}
    </ul>
  );
}
