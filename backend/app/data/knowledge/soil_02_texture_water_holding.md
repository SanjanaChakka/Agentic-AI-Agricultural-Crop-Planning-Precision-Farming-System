---
doc_key: soil.texture_and_water_holding
title: Soil texture, field capacity and plant-available water
category: soil_conditions
organisation: Project reference note compiled from USDA NRCS soil survey guidance
source_url: https://www.nrcs.usda.gov/
region: global
year: 2024
---
# Soil texture and plant-available water

Texture controls how much water a soil can hold and how quickly it releases it
to plant roots. Coarse textures (sand, sandy loam) hold little water and require
frequent light irrigations; fine textures (clay, clay loam, black soils) hold
much more but can lose large amounts of water to deep percolation if irrigating
at full field capacity.

Approximate volumetric water content at field capacity, the refill trigger and
wilting point used by this project (% VWC):

- sandy: 18 / 10 / 6, plant-available water about 8 mm per 10 cm
- sandy loam: 26 / 15 / 9, about 12 mm per 10 cm
- loam: 33 / 21 / 13, about 17 mm per 10 cm
- silt loam: 36 / 23 / 14, about 19 mm per 10 cm
- clay loam: 38 / 25 / 15, about 20 mm per 10 cm
- clay: 42 / 27 / 18, about 18 mm per 10 cm
- black soil (vertic clay): 40 / 26 / 17, about 20 mm per 10 cm
- red soil: 27 / 17 / 10, about 13 mm per 10 cm
- red laterite: 25 / 15 / 9, about 11 mm per 10 cm
- alluvial: 34 / 22 / 13, about 17 mm per 10 cm

Practical consequences:

- A sensor reporting volumetric water content must be calibrated for the
  texture it is installed in. Uncalibrated capacitance probes can read several
  percent low in clay soils.
- The refill trigger is roughly half of field capacity. Irrigation is normally
  triggered at or slightly above it, not at wilting point.
- Waterlogging risk rises sharply when a clay or black soil receives more water
  than its field capacity in a short window, because air-filled porosity drops
  and roots suffocate even though the soil appears wet.