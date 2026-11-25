# Preventive Maintenance Plan

Synthetic demo content for the Fabric Demo Gallery. Not for use on real equipment.

The plan runs 5 production lines (Line-A to Line-E) on three 8-hour shifts:
Night 00:00-08:00, Day 08:00-16:00, Evening 16:00-24:00. Preventive maintenance
(PM) is scheduled in planned stops. Unplanned downtime above 60 minutes in one
batch must be reported in the shift handover.

## Base intervals by machine type

| Machine type | Daily (operator) | Weekly | Monthly | Quarterly |
|---|---|---|---|---|
| Injection Molder | Check barrel zone temps, purge nozzle | Grease tie bars, check hydraulic oil | Check-ring and screw wear check, heater band resistance | Hydraulic oil analysis, platen alignment |
| Stamping Press | Check air pressure, lubrication level | Gib clearance check, bolster clamp torque | Clutch/brake stopping-time test | Flywheel bearing vibration analysis |
| CNC Mill | Clean chips, check coolant concentration | Spindle taper clean, way lube level | Spindle vibration check, backlash test | Ballscrew inspection |
| Lathe | Check chuck pressure, coolant | Way wiper inspection | Turret indexing accuracy | Spindle bearing check |
| Welding Robot | Replace contact tip as needed, clean nozzle | Coolant flow check (≥ 1.2 l/min), cable dress | Axis vibration test (J1-J6) | Reducer grease change |
| Assembly Arm | Check gripper pressure (≥ 5.5 bar) | Encoder cable inspection | Repeatability test (≤ 0.5 mm) | Belt tension and harmonic drive check |

## Age-based adjustment

Machine age is calculated from the install date in the equipment catalog.

- **Under 3 years:** base intervals.
- **3-6 years:** add a monthly vibration check for all machine types.
- **Over 6 years:** halve the weekly and monthly intervals, and run vibration
  analysis every two weeks. These machines have the highest failure rate in the plant.

## Prioritizing the PM backlog

When capacity is limited, rank machines by:

1. A failure event in the last 7 days (any batch with `failure_event = 1`).
2. Daily average vibration or temperature above the warning limit (see Sensor Limits).
3. Machine age over 6 years.
4. Machine types with the highest failure rates: Welding Robot, Stamping Press, Injection Molder.
5. Total downtime minutes in the last 14 days.

## Critical spare parts to keep in stock

- Stamping Press: gib liners, flywheel bearing set, brake lining kit.
- Injection Molder: heater bands (all zones), thermocouples, check-ring.
- Welding Robot: contact tips (50+), nozzles, J2/J3 reducer (1 per 4 robots).
- CNC Mill: spindle drawbar springs, tool holders.
