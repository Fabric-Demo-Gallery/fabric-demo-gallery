# Quality Hold Procedure

Synthetic demo content for the Fabric Demo Gallery. Not for production use.

A quality hold blocks a production batch from shipping until quality has
re-inspected it. Holds are placed in the plant maintenance system, which returns a
hold ID (format `QH-YYMMDD-HHMMSS`). A hold only exists once the system has returned
its ID - never quote a hold ID that the system did not return.

## Batch defect rate

Defect rate = defect_count / units_produced of the batch. The plant's normal level is
about 5 %; a line or shift above 6 % is investigated.

## When to act

| Batch defect rate | Action |
|---|---|
| Up to 8 % | Normal. No action. |
| Above 8 % and up to 10 % | **Watch:** increase sampling to 1 in 10 parts for the next batch on the same machine. No hold. |
| Above 10 % | **Hold:** place a quality hold for the batch, then re-inspect 100 % of it. |
| Any Critical defect (see the Quality Inspection Standard) | **Hold** regardless of the defect rate. |

Batches that had an equipment failure (`failure_event = 1`) and a defect rate above
8 % must be named in the shift handover, even if they are not on hold.

## Placing a hold

Place one hold per batch. Each hold records:

1. **Batch ID** (for example `B-04049`).
2. **Machine ID** that produced the batch.
3. **Reason** - the defect rate with the numbers (defects / units produced), the
   failure event if any, and the suspected cause.
4. **Placed by** - the person or the agent.

## Releasing a hold

Quality releases the batch after the 100 % re-inspection, and only when the
machine's corrective work order (see the Work Order Procedure) is done or the cause
has been ruled out. Reject parts are scrapped or reworked and recorded.
