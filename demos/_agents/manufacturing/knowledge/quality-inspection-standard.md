# Quality Inspection Standard

Synthetic demo content for the Fabric Demo Gallery. Not for production use.

The plant makes five products: Widget-A, Gear-X, Bracket-Z, Valve-Q and Rotor-M.
This standard defines how visual defects are classified and how engineering
drawings are reviewed before release.

## Severity classes

| Class | Definition | Action |
|---|---|---|
| Critical | Could cause a safety risk or functional failure in use | Reject. Quarantine the batch, notify the quality engineer. |
| Major | Likely to cause an assembly or fit problem, or a customer complaint | Reject the part. Inspect 100 % of the batch. |
| Minor | Cosmetic only, no effect on function or fit | Accept if within the limits below. Record it. |

## Defect catalog by process

### Injection molding (Widget-A, Valve-Q housings)
- **Short shot:** incomplete fill → Major (Critical on sealing surfaces).
- **Flash:** excess material at the parting line. ≤ 0.2 mm Minor, > 0.2 mm Major.
- **Sink marks:** depressions over thick sections. Visible on a cosmetic face → Minor.
- **Warpage:** > 0.5 mm over 100 mm → Major.
- **Burn marks / black specks:** Minor; Major on transparent parts.

### Stamping (Bracket-Z)
- **Burr:** > 0.1 mm height → Major (cut hazard, fit issue).
- **Crack or split:** any → Critical.
- **Wrinkle:** on a formed flange → Major.
- **Dent / scratch:** cosmetic face only → Minor if < 5 mm.

### Machining (Gear-X, Rotor-M, Valve-Q)
- **Out-of-tolerance dimension:** Major. Critical on bearing or sealing diameters.
- **Chatter marks:** Ra above the drawing value → Major.
- **Tool marks / scratches:** Minor on non-functional faces.
- **Gear tooth chip:** Critical.

### Welding (Rotor-M frames, Bracket-Z sub-assemblies)
- **Crack:** Critical.
- **Incomplete fusion / lack of penetration:** Critical.
- **Porosity:** surface pores > 1 mm or > 3 per 100 mm → Major.
- **Undercut:** > 0.5 mm → Major.
- **Spatter:** Minor; remove it before painting.
- Process causes to check for porosity and heavy spatter: shielding gas flow,
  a clogged nozzle or gas diffuser, a worn contact tip, torch overheating (alarm
  WR-180), and oil or rust on the base metal.

### Assembly
- **Missing fastener or part:** Critical.
- **Misalignment:** > 0.5 mm → Major.

## Reporting a visual inspection

For every inspected item, state:

1. Part/product, if identifiable.
2. Each defect with its type, location, approximate size, and severity class from this standard.
3. A verdict: Accept, Accept with record, or Reject.
4. A recommended next step, such as a process cause to check.
5. Your confidence. If the image is unclear, say what additional view or measurement is needed.

## Drawing review checklist

A drawing may be released only if all items are satisfied:

1. **Title block** complete: title, drawing number, revision, material, units,
   scale, sheet, drawn/checked/approved names and dates.
2. **Units** stated (mm), and a general tolerance note present (for example ISO 2768-m).
3. **Every functional feature dimensioned once**, with no redundant or missing dimensions.
4. **Tolerances** on all fits, bores, and mating features.
5. **Datums** defined (A, B, C) for every GD&T callout that references them.
6. **GD&T** symbols are valid and reference existing datums.
7. **Surface finish** specified on functional surfaces (Ra value).
8. **Notes:** deburring, edge breaks, heat treatment or coating where relevant.
9. **Views** are sufficient to define the part unambiguously.

Report each item as OK / Missing / Unclear, then give a release recommendation.
