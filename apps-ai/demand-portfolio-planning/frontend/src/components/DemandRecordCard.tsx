import type { DemandRecord, TrackedField } from "../types";
import type { Key } from "../i18n";
import { useT } from "../I18nProvider";
import { FieldRow, ItemList } from "./fields";

const SCALAR_FIELDS = [
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
] as const;

type ScalarField = (typeof SCALAR_FIELDS)[number];

export function DemandRecordCard({
  record,
  onEditField,
  rechecking = false,
  version,
}: {
  record: DemandRecord;
  onEditField?: (field: ScalarField, value: string) => void;
  rechecking?: boolean;
  version?: number;
}) {
  const t = useT();
  return (
    <section className="card">
      <h2 className="card-title">
        {t("record.heading")}
        {version && version > 1 ? <span className="ver-badge">v{version}</span> : null}
        {rechecking && (
          <span className="recheck-chip">
            <span className="spinner spinner-sm" aria-hidden="true" />
            {t("working.precheck")}
          </span>
        )}
      </h2>
      <div className="field-grid">
        {SCALAR_FIELDS.map((name) => (
          <FieldRow
            key={name}
            label={t(`field.${name}` as Key)}
            field={record[name] as TrackedField}
            onEdit={onEditField ? (value) => onEditField(name, value) : undefined}
          />
        ))}
      </div>

      {record.subject_matter_experts.length > 0 && (
        <div className="card-block">
          <h3 className="block-title">{t("record.smes")}</h3>
          <ItemList items={record.subject_matter_experts} />
        </div>
      )}
      {record.open_questions.length > 0 && (
        <div className="card-block">
          <h3 className="block-title">{t("record.open_questions")}</h3>
          <ItemList items={record.open_questions} />
        </div>
      )}
      {record.conflicts.length > 0 && (
        <div className="card-block">
          <h3 className="block-title conflict-title">{t("record.conflicts")}</h3>
          <ul className="item-list">
            {record.conflicts.map((c, i) => (
              <li key={i} className="item-row conflict-row">
                <strong>{c.field}:</strong> {c.description}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
