---
doc_key: practices.sensor_data_quality
title: Field sensor networks, calibration and data quality
category: sensor_pipeline
organisation: Project reference note compiled from FAO and open-source IoT agriculture guidance
source_url: https://www.fao.org/
region: global
year: 2024
---
# Sensor networks and data quality

Capacitance-based soil moisture probes report volumetric water content, but they
must be calibrated for the soil texture and installation depth. A probe
calibrated in a sandy loam can read several percent low in a heavy clay. Report
the calibration alongside the reading.

Common data-quality signals that indicate a sensor problem rather than a soil
change:

- A reading identical to the previous reading over many intervals (stuck
  value).
- A step change larger than physically plausible without irrigation or rain.
- Values outside the physically possible range - for example negative moisture
  or volumetric content above 60 percent in a non-paddy soil.
- Values drifting steadily in one direction for more than a week.
- Air temperature readings above roughly 55 degrees C in the shade, which
  almost always indicates a wiring, units or placement fault.
- Missing or null fields in an otherwise regular series.

Handling rules used by this system:

- Flag suspect readings, retain the raw value, and exclude flagged readings
  from trend statistics.
- Never silently substitute an imputed value for a measured one; if a value is
  missing it stays missing and is reported as missing.
- Track the gap between readings. A gap longer than twice the expected
  reporting interval is itself an alerting condition.
- Simulated data must be marked as simulated and must never be blended with
  real readings without a visible distinction.

Common instrumentation in a smallholder field system: one soil moisture and
soil temperature probe at 20 cm and 40 cm, one air temperature and relative
humidity sensor in a ventilated radiation shield at canopy height, a tipping
bucket or capacitive rain gauge, and a flow meter on the irrigation pump line.