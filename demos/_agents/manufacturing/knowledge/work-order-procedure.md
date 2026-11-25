# Maintenance Work Order Procedure

Synthetic demo content for the Fabric Demo Gallery. Not for use on real equipment.

Every corrective or preventive job on a machine is tracked as a work order in the
plant maintenance system (CMMS). A work order is only real once the maintenance
system has returned its ID (format `WO-YYMMDD-HHMMSS`). Never quote a work order ID
that the system did not return.

## Priorities

| Priority | When to use | Response time | Who approves |
|---|---|---|---|
| P1 - Emergency | Safety risk, fire, injury risk, or the line is stopped | Start within 1 hour | Shift lead (verbal, record afterwards) |
| P2 - Urgent | Equipment failure or an alarm that causes defects or downtime on a running line (a failure event in the last 7 days, or a batch defect rate above 8 %) | Start within the current or next shift | Maintenance supervisor |
| P3 - Planned | Warning-level sensor trend, overdue preventive maintenance, or machine age over 6 years with no failure yet | Within 7 days, in a planned stop | Maintenance planner |
| P4 - Improvement | Cosmetic issues, housekeeping, improvement ideas | Next planned shutdown | Maintenance planner |

If in doubt between two priorities, choose the higher one and say why.

## What a work order must contain

1. **Machine ID** from the equipment catalog (for example `MCH-0046`).
2. **Priority** P1-P4 from the table above.
3. **Title** - under 80 characters: the machine type, the symptom and the job,
   for example "Welding Robot MCH-0046: porosity - clean nozzle, replace contact tip".
4. **Description** - the evidence (alarm codes, sensor values with units, failure
   events, defect rate), then the ordered tasks, the spare parts needed, and the
   Lockout/Tagout reminder.
5. **Requested by** - the person or the agent that raised it.

## Approval before creation

Work orders raised from an incident are proposed first and created only after the
approver in the table above has approved them. A rejected proposal is not created;
record the reason in the shift handover.

## Escalation

- A P1 or P2 work order on a Welding Robot, Stamping Press or Injection Molder is
  also reported to the production manager, because these machine types cause most
  of the plant's failures.
- Two P2 work orders on the same machine within 14 days: request a root-cause
  analysis by the reliability engineer.
- A quality hold linked to a machine (see the Quality Hold Procedure) makes the
  related work order at least P2.

## Closing a work order

The technician records the work done, the parts used and the downtime. The machine
is released to production only after a first-off part passes inspection.
