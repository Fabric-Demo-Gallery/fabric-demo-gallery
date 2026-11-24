# Alarm Code Reference

Synthetic demo content for the Fabric Demo Gallery. Not for use on real equipment.

Alarm codes start with a two-letter machine-type prefix. Before opening any guard,
door, or die area, follow the Lockout/Tagout procedure.

Sensor units used below: temperature in °C, hydraulic/pneumatic pressure in bar,
vibration in mm/s RMS, humidity in %RH. Thresholds per machine type are in the
Sensor Limits standard.

## Injection Molder (IM)

### IM-101 Barrel temperature deviation
- Meaning: a barrel heater zone is more than 8 °C away from its setpoint for over 2 minutes.
- Typical sensor signature: machine temperature above the warning limit while pressure is normal.
- Likely causes: failed heater band, loose thermocouple, wrong material setpoint.
- First checks, in order:
  1. Compare the zone setpoint against the material data sheet.
  2. Check the thermocouple seating and wiring.
  3. Measure the heater band resistance (expected 25-40 Ω).
- Escalate when: the deviation returns within 1 hour after reset.
- Typical repair time: 30-60 minutes.

### IM-204 Hydraulic pressure high
- Meaning: injection hydraulic pressure is above the warning limit for 3 consecutive cycles.
- Typical sensor signature: pressure and temperature rising together.
- Likely causes: blocked nozzle, cold slug, viscosity too high (melt too cold), worn check ring.
- First checks:
  1. Purge the barrel and inspect the nozzle for blockage.
  2. Verify melt temperature against the setpoint.
  3. Review the check-ring wear history in the maintenance log.
- Escalate when: pressure stays above the alarm limit after purging.
- Typical repair time: 45-90 minutes; check-ring replacement 4 hours.

### IM-415 Platen vibration high
- Meaning: vibration on the moving platen is above the warning limit.
- Typical sensor signature: vibration rising over several days, often with temperature.
- Likely causes: worn tie-bar bushings, misaligned mold, loose platen bolts.
- First checks:
  1. Check the mold alignment and clamp bolts.
  2. Grease the tie bars.
  3. Run a vibration spectrum for bushing wear.
- Escalate when: vibration exceeds the alarm limit, or the machine is older than 6 years.
- Typical repair time: 2-6 hours.

## Stamping Press (SP)

### SP-117 Clutch/brake response slow
- Meaning: the stopping time is above 180 ms.
- Likely causes: worn brake lining, low air pressure, contaminated valve.
- First checks:
  1. Verify the supply air pressure.
  2. Run the stopping-time test.
  3. Inspect the brake lining thickness (minimum 4 mm).
- Safety: the press must not run until the stopping time is within limits.
- Typical repair time: 2-4 hours.

### SP-214 Ram vibration high
- Meaning: vibration at the ram/slide is above the warning limit for more than 5 minutes.
- Typical sensor signature: vibration above the warning limit, often with pressure above 150 bar.
- Likely causes: excessive gib clearance, worn flywheel bearing, die not seated or unbalanced load.
- First checks, in order:
  1. Stop the press and apply Lockout/Tagout.
  2. Check that the die is seated and the bolster clamps are torqued (350 Nm).
  3. Measure the gib clearance (allowed 0.05-0.15 mm; adjust if above 0.15 mm).
  4. Listen to and measure the flywheel bearing (vibration analysis); grease per the PM plan.
- Escalate when: vibration exceeds the alarm limit, the alarm repeats within one shift, or the press is older than 6 years.
- Typical repair time: gib adjustment 1-2 hours; flywheel bearing replacement 8-12 hours.

### SP-320 Tonnage overload
- Meaning: the measured tonnage exceeded 105 % of the die rating.
- Likely causes: double blank, wrong material thickness, incorrect shut height.
- First checks:
  1. Remove the part and inspect for a double blank.
  2. Verify the coil thickness.
  3. Re-check the shut height.
- Typical repair time: 30 minutes. If repeated, run a die inspection (2 hours).

## CNC Mill (CM)

### CM-150 Spindle temperature high
- Meaning: spindle bearing temperature is above the warning limit.
- Likely causes: insufficient lubrication, worn spindle bearings, excessive feed or speed.
- First checks:
  1. Check the spindle oil/air lubrication flow.
  2. Reduce feed and speed by 20 % and observe.
  3. Run a spindle vibration check.
- Escalate when: the alarm limit is reached. Spindle rebuilds are vendor work (2-3 days).

### CM-230 Spindle vibration high
- Meaning: spindle vibration is above the warning limit.
- Likely causes: tool imbalance, worn tool holder, bearing damage.
- First checks:
  1. Replace the tool and holder.
  2. Clean the spindle taper.
  3. Re-measure. If vibration persists, the bearings are suspect.

## Lathe (LT)

### LT-140 Chuck pressure low
- Meaning: hydraulic chuck clamping pressure is below 80 % of its setpoint.
- Likely causes: leaking rotary cylinder, low hydraulic oil.
- First checks:
  1. Check the hydraulic oil level.
  2. Inspect the rotary cylinder for leaks.
- Safety: do not run; risk of part ejection.

### LT-260 Turret vibration high
- Meaning: turret or carriage vibration is above the warning limit.
- Likely causes: worn way wipers, loose gib, chatter from tooling.
- First checks:
  1. Check the tool overhang and insert wear.
  2. Inspect the way wipers.
  3. Check the gib adjustment.

## Welding Robot (WR)

### WR-180 Torch temperature high
- Meaning: the welding torch or cable temperature is above the warning limit.
- Typical sensor signature: temperature above the warning limit, often with high duty cycle.
- Likely causes: coolant flow too low, clogged coolant line, worn contact tip.
- First checks:
  1. Check that coolant flow is at least 1.2 l/min.
  2. Replace the contact tip and nozzle.
  3. Clean spatter from the gas diffuser.
- Escalate when: the alarm limit is reached, or the alarm repeats within 2 shifts.
- Typical repair time: 20-45 minutes.

### WR-245 Axis vibration high
- Meaning: vibration on a robot axis (usually J2/J3) is above the warning limit.
- Likely causes: reducer (gearbox) wear, loose base bolts, cable dress pulling on the arm.
- First checks:
  1. Torque the base bolts.
  2. Check the cable dress.
  3. Run the axis vibration test from the teach pendant.
- Escalate when: the alarm limit is reached. Reducer replacement is vendor work (1-2 days).

## Assembly Arm (AA)

### AA-110 Gripper pressure low
- Meaning: the pneumatic gripper pressure is below 5.5 bar.
- First checks:
  1. Check the air supply and filter regulator.
  2. Inspect the gripper seals.

### AA-205 Positioning error
- Meaning: the arm missed its taught position by more than 0.5 mm.
- First checks:
  1. Re-home the arm.
  2. Check the encoder cable.
  3. Re-teach the point if the fixture was moved.
