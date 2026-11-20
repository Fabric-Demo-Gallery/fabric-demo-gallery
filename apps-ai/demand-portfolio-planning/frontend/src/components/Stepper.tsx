import { useT } from "../I18nProvider";
import type { Key } from "../i18n";

export type StepId =
  | "intake"
  | "precheck"
  | "board"
  | "portfolio"
  | "resource"
  | "plan"
  | "handoff";

export const STEPS: StepId[] = [
  "intake",
  "precheck",
  "board",
  "portfolio",
  "resource",
  "plan",
  "handoff",
];

const STEP_KEY: Record<StepId, Key> = {
  intake: "step.intake",
  precheck: "step.precheck",
  board: "step.board",
  portfolio: "step.portfolio",
  resource: "step.resource",
  plan: "step.plan",
  handoff: "step.handoff",
};

export function Stepper({
  current,
  visitable,
  onSelect,
}: {
  current: StepId;
  visitable?: Set<StepId>;
  onSelect?: (step: StepId) => void;
}) {
  const t = useT();
  const activeIndex = STEPS.indexOf(current);
  return (
    <nav className="stepper" aria-label="pipeline">
      {STEPS.map((step, i) => {
        const state = i < activeIndex ? "done" : i === activeIndex ? "active" : "pending";
        const clickable = Boolean(onSelect && visitable?.has(step));
        return (
          <button
            type="button"
            className={`step step-${state}${clickable ? " step-clickable" : ""}`}
            key={step}
            disabled={!clickable}
            onClick={() => clickable && onSelect?.(step)}
          >
            <span className="step-marker">{state === "done" ? "✓" : i + 1}</span>
            <span className="step-label">{t(STEP_KEY[step])}</span>
          </button>
        );
      })}
    </nav>
  );
}
