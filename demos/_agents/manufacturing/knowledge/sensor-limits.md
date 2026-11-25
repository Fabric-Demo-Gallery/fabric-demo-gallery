# Sensor Limits Standard

Synthetic demo content for the Fabric Demo Gallery. Not for use on real equipment.

Every machine reports temperature (°C), pressure (bar), vibration (mm/s RMS) and
humidity (%RH) several times per hour. The limits below apply to individual
readings. A daily average above the warning limit counts as a trend and must be
reviewed by maintenance within 24 hours.

## How to read the limits

- **Normal**: the expected operating band.
- **Warning**: plan maintenance within 48 hours and inspect at the next stop.
- **Alarm**: stop the machine at the next safe point and raise a maintenance work order immediately.

## Limits by machine type

| Machine type | Temperature normal | Temp warning | Temp alarm | Pressure normal | Pressure warning | Pressure alarm | Vibration normal | Vibration warning | Vibration alarm |
|---|---|---|---|---|---|---|---|---|---|
| Assembly Arm | 62-91 | > 94 | > 99 | 104-149 | > 154 | > 167 | 1.1-4.5 | > 4.8 | > 5.7 |
| CNC Mill | 65-92 | > 95 | > 100 | 107-153 | > 157 | > 168 | 1.5-4.7 | > 5.1 | > 6.2 |
| Injection Molder | 67-94 | > 96 | > 104 | 110-157 | > 161 | > 173 | 1.6-5.0 | > 5.2 | > 6.0 |
| Lathe | 63-94 | > 95 | > 101 | 105-153 | > 156 | > 166 | 1.2-4.7 | > 5.0 | > 5.6 |
| Stamping Press | 68-91 | > 93 | > 99 | 110-152 | > 155 | > 166 | 1.6-4.6 | > 4.9 | > 5.7 |
| Welding Robot | 68-95 | > 97 | > 104 | 113-157 | > 161 | > 171 | 1.7-5.0 | > 5.3 | > 6.1 |

Humidity: 37-54 %RH is normal for all machine types. Above 60 %RH, check the hall
ventilation; this is not a machine fault.

## Combined signals

- Temperature and vibration both above warning on the same machine on the same
  day is the strongest early sign of a failure. Treat it as an alarm.
- Rising daily averages over 3 or more consecutive days are more important than a
  single high reading.
- Machines older than 6 years fail roughly twice as often as machines under 3
  years. Use the warning limit as the alarm limit for them.
