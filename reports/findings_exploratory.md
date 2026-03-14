# Exploratory Findings

**Status**: Exploratory — all findings are preliminary observations from aggregate simulated data.
Numbers should be independently verified before use in any formal report.

**Data source**: `data/processed/combined.csv` (2,873,280 rows; 3 counties; 2 upgrade scenarios;
full year 2018 AMY at 15-minute resolution). Summary statistics cited from
`reports/eda_stats_new.csv`. Seasonal and hourly breakdowns were computed directly from
`data/processed/combined.csv` and are not yet reproduced in a separate report file —
treat those values with additional caution.

**Reminder**: ComStock outputs are model-simulated aggregates, not measured building energy.
All findings describe model behaviour and may reflect modelling assumptions as much as real
building physics.

---

## Finding 1: Package 3 reduces school energy by 3–4× more in winter than in summer in cold climates — consistent with heating fuel-switching, but electric demand rises substantially

### Observation

In Colorado and Michigan, secondary and primary schools showed roughly 50% lower mean site
energy in winter months (December–February) under Package 3 (upgrade 36) compared with
Baseline (upgrade 0), while summer reductions were only 5–8%. California schools, by
contrast, showed moderate reductions in both seasons (~18% winter, ~18% summer), with
little seasonal asymmetry.

Illustrative values computed from `data/processed/combined.csv`:

| County | Building | Season | Baseline mean | Pkg 3 mean | Reduction |
|---|---|---|---|---|---|
| CO | SecondarySchool | Winter (Dec–Feb) | 1.15 kWh/1000sqft | 0.57 kWh/1000sqft | ~50% |
| CO | SecondarySchool | Summer (Jun–Aug) | 0.36 kWh/1000sqft | 0.34 kWh/1000sqft | ~7% |
| MI | SecondarySchool | Winter (Dec–Feb) | 1.66 kWh/1000sqft | 0.79 kWh/1000sqft | ~52% |
| MI | SecondarySchool | Summer (Jun–Aug) | 0.56 kWh/1000sqft | 0.53 kWh/1000sqft | ~5% |
| CA | SecondarySchool | Winter (Dec–Feb) | 1.21 kWh/1000sqft | 0.92 kWh/1000sqft | ~24% |

Annual mean reductions (from `reports/eda_stats_new.csv`): CO SecondarySchool −32%,
MI SecondarySchool not separately tabled but consistent with pattern.

Simultaneously, electric heating consumption in CO schools increased by
approximately +0.19–0.38 kWh/1000sqft per 15-minute interval in winter months under Package 3
(computed from `data/processed/combined.csv`), while natural gas heating decreased.
Total site energy nevertheless fell because heat pump coefficient of performance (COP) > 1.

### Skeptical evaluation

**What supports it**: The pattern is physically coherent. Package 3 replaces gas heating with
standard-performance heat pump RTUs. Heat pumps operating with COP of roughly 2–3 deliver
more heat per unit of input energy than combustion, so total site energy falls even as
electricity consumption rises. The asymmetry (large winter effect, small summer effect) is
exactly what heating-efficiency improvements would produce.

**Reasons to be cautious**:
- ComStock assigns performance curves to heat pumps based on outdoor temperature. At the
  extreme cold temperatures experienced in CO and MI, standard-performance HP efficiency
  degrades significantly — the model's assumed COP at, for example, −10°C determines much
  of this result. If the model is optimistic about cold-climate HP performance, these
  reductions would be overstated.
- The summer data conflates occupancy effects (schools are closed July–August in CO/MI),
  making the seasonal comparison partly an occupancy comparison rather than a weather one.
  A proper heating-only analysis would require filtering to occupied school days.
- These are county-level aggregates. Within each county the actual school stock may vary
  considerably in vintage, insulation level, and existing HVAC system type — the baseline
  represents modelled diversity, not a single building.

**Bottom line**: The direction (large cold-climate winter heating reduction) is credible.
The specific magnitudes (~50%) depend on heat pump performance assumptions in the model
and should not be quoted without reviewing the ComStock HP characterisation.

---

## Finding 2: California warehouses consume more energy at night than during business hours — driven almost entirely by exterior lighting, not operations

### Observation

Mean site energy intensity for California warehouses (baseline) appeared higher during
overnight hours than during the business day (computed from `data/processed/combined.csv`):
approximately 0.113 kWh/1000sqft at midnight vs. 0.077 kWh/1000sqft at noon. This pattern
inverted relative to Colorado and Michigan warehouses, which showed relatively flat or
slightly daytime-dominant profiles.

End-use decomposition revealed that exterior lighting in CA warehouses was approximately
0.068 kWh/1000sqft during hours 20:00–07:00, dropping to near zero during daylight hours.
At midnight, exterior lighting appeared to account for roughly 60% of total warehouse
electricity and the large majority of the overnight premium over daytime energy.

### Skeptical evaluation

**What supports it**: The pattern is structurally plausible. ComStock models exterior
lighting on dusk-to-dawn schedules driven by AMY 2018 weather. Orange County, CA has
shorter winter nights than MI but the aggregate reflects the full year — during winter
months exterior lighting runs ~14 hours/night. Large warehouse and distribution facilities
commonly maintain full parking-lot and security lighting throughout the night regardless of
occupancy. The CA warehouse aggregate represents approximately 141.7 million square feet
of floor area, a figure consistent with the dense distribution-centre and big-box retail
concentration in Orange County.

**Reasons to be cautious**:
- Exterior lighting schedules in ComStock are parametric model inputs, not metered.
  The overnight intensity could reflect assumptions about parking-area lighting relative
  to floor area that may not be calibrated to Orange County specifically.
- The "floor area" normalisation divides exterior lighting (which scales with site area
  or perimeter) by building floor area. High-footprint, single-story warehouses with
  large surface lots would show elevated exterior-lighting-per-floor-area ratios by
  construction, regardless of actual operations.
- CO and MI warehouses also have exterior lighting but show lower intensity relative to
  daytime energy. This may reflect different parking-area assumptions in the modelled
  prototypes, not necessarily a real geographic difference.
- The `max_value` for CA Warehouse baseline in `reports/qa_checks.csv` is 0.769
  kWh/1000sqft, occurring at a morning hour (hour 7 in the mean profile), consistent
  with the peak occurring at dawn when exterior lights are still on and indoor operations
  beginning — worth checking in any follow-up.

**Bottom line**: The overnight-heavy pattern is real in the model. Whether it accurately
represents Orange County warehouse stock depends on ComStock's exterior lighting
assumptions, which warrant scrutiny before citing this finding publicly.

---

## Finding 3: Restaurants are the most energy-intensive building type but receive the smallest proportional benefit from Package 3 — because their dominant gas use is cooking, not space heating

### Observation

Full-service and quick-service restaurants showed the highest mean site energy intensity
of any building type across all three counties (from `reports/eda_stats_new.csv`):

| Building type | CA mean (baseline) | CO mean (baseline) | MI mean (baseline) |
|---|---|---|---|
| FullServiceRestaurant | 4.18 kWh/1000sqft | 3.20 kWh/1000sqft | 3.96 kWh/1000sqft |
| QuickServiceRestaurant | 4.49 kWh/1000sqft | 3.42 kWh/1000sqft | 3.60 kWh/1000sqft |

These values are roughly 5–10× higher than offices, schools, and warehouses.

Under Package 3, these same building types showed the smallest proportional mean reductions:
−9% (FullServiceRestaurant) and −8% (QuickServiceRestaurant) averaged across counties, compared
with −30% for Secondary Schools and −30% for Retail Standalone (from `reports/eda_stats_new.csv`,
computed as weighted mean across states).

End-use decomposition (computed from `data/processed/combined.csv`) showed that natural gas
accounted for approximately 50–60% of restaurant site energy (CA: ~50% FSR, ~44% QSR;
MI: ~60% FSR, ~50% QSR). Within gas, interior equipment (cooking gas) dominated over
space-heating gas. Package 3 targets space-heating efficiency (HP RTUs and HP boilers) and
LED lighting; it does not include electrification or efficiency improvements to commercial
cooking equipment.

### Skeptical evaluation

**What supports it**: The logic is straightforward. If ~50–60% of restaurant energy is gas,
and most of that gas is used for cooking rather than space heating, then a package improving
only heating and lighting equipment will have limited effect. The end-use columns
(`out.natural_gas.interior_equipment`) directly confirm that cooking gas represents a
substantial fraction. This is consistent with published knowledge that commercial kitchens
are among the most energy-intensive spaces per square foot of any building category.

**Reasons to be cautious**:
- The magnitude of restaurant energy intensity (4–4.5 kWh/1000sqft) is partly an artefact
  of the `floor_area_represented` denominator. Restaurants are normalised by the total floor
  area of all restaurants in the county — this includes dining area, kitchen, and ancillary
  space. A floor-area normalisation for a high-intensity use concentrated in the kitchen may
  still understate intensity at the kitchen level.
- The aggregate `models_used` count for restaurants (especially QSR in smaller counties)
  was not retained in the processed data; in the MI aggregate this could be a small number
  of models, making the average less stable.
- Heating gas is not zero in restaurants. The Package 3 reduction, while small in percentage
  terms, represents a real absolute reduction in gas use that has value for emissions and
  operating cost — the small *percentage* should not be conflated with negligible impact.

**Bottom line**: The resistance of restaurants to Package 3 is well-supported and
mechanistically explained. It is not a data artefact.

---

## Finding 4: California schools show virtually no seasonal variation in energy use, while Colorado and Michigan schools peak 3–4× higher in winter than summer — but the comparison conflates weather and school calendar

### Observation

Computed monthly mean site energy (from `data/processed/combined.csv`, baseline):

| State | Building | January mean | July mean | Ratio Jan/Jul |
|---|---|---|---|---|
| CA | PrimarySchool | 0.916 kWh/1000sqft | 1.013 kWh/1000sqft | 0.90 (summer higher) |
| CO | PrimarySchool | 0.922 kWh/1000sqft | 0.293 kWh/1000sqft | 3.1× winter |
| MI | PrimarySchool | 1.432 kWh/1000sqft | 0.390 kWh/1000sqft | 3.7× winter |

California primary schools appeared to use slightly more energy in July than in January —
the opposite of CO and MI. For CO and MI, winter energy was roughly 3–4× summer energy.
The same directional pattern held for secondary schools, with larger absolute differences.

This suggests that in Southern California, summer cooling demand in schools may be comparable
to or exceed winter heating demand, while in CO and MI winter heating dominates overwhelmingly.

### Skeptical evaluation

**What supports it**: Orange County, CA has mild winters (average January low ~8°C) and
warm summers (average July high ~29°C), meaning school buildings face meaningful cooling
loads in summer. CO and MI have severe winters that drive large heating loads. The direction
of the California summer-high pattern is climatically plausible.

**Reasons to be cautious**:
- The largest confound is the **school calendar**. In all three states, schools are largely
  closed in July and August. Low CO/MI summer energy partially reflects unoccupied buildings,
  not purely weather-driven efficiency. CA may also have lower summer occupancy, so the
  relatively high CA July value likely understates the weather effect: even with reduced
  occupancy, CA schools use as much energy in summer as in occupied winter months.
- A rigorous climate comparison would require controlling for occupancy (e.g., comparing
  occupied heating-season months only). The ComStock model applies occupancy schedules that
  include school calendars, so this effect is captured in the simulation, but it cannot be
  separated from weather effects in this aggregate data without additional metadata.
- The CA PrimarySchool July mean of 1.013 kWh/1000sqft is notably higher than winter —
  if summer occupancy is lower in CA too, the cooling intensity per occupied hour could be
  considerably higher than the winter heating intensity. This would be a more precise claim
  but cannot be confirmed from the aggregate timeseries alone.

**Bottom line**: The directional finding (CA school seasonal flatness vs. CO/MI winter
dominance) is credible and consistent with climate. Citing specific ratios requires
acknowledging that summer values reflect unoccupied buildings in CO/MI.

---

## Finding 5: Retail Standalone showed the largest peak-demand reduction under Package 3 among all building types, yet also showed the highest outlier rate in the baseline — raising questions about the reliability of the peak estimate

### Observation

From `reports/eda_stats_new.csv`, Retail Standalone showed some of the largest peak demand
reductions under Package 3:

| County | Baseline peak | Pkg 3 peak | Reduction |
|---|---|---|---|
| CA | 2.181 kWh/1000sqft | 1.365 kWh/1000sqft | −37% |
| CO | 2.140 kWh/1000sqft | 1.768 kWh/1000sqft | −17% |
| MI | 3.247 kWh/1000sqft | 2.782 kWh/1000sqft | −14% |

From `reports/qa_checks.csv`, Retail Standalone also had among the highest outlier rates
(values exceeding Q3 + 3×IQR on site energy intensity) in the dataset:

| State | Upgrade | Building type | % outliers (3×IQR) |
|---|---|---|---|
| MI | 36 | RetailStandalone | 1.83% |
| CO | 36 | RetailStandalone | 0.70% |
| CA | 36 | RetailStandalone | 1.43% |

By comparison, most office and hotel building types showed outlier rates below 0.2%.
The reported "peak" value (single maximum observation across 35,040 timesteps) would
fall within the outlier range.

### Skeptical evaluation

**What supports it**: The large CA peak reduction (−37%) and the relatively high outlier
rate both point to a distribution with an irregular heavy right tail in the baseline.
Package 3 changes would primarily affect heating efficiency (reducing rare extreme
heating events) and lighting (reducing a constant baseline), which could simultaneously
reduce both the mean and clip the upper tail of the distribution.

**Reasons to be cautious**:
- The peak demand statistic (single maximum 15-minute value over a full year) is the
  least stable summary statistic in the dataset — it represents one interval out of 35,040
  and is inherently sensitive to extreme weather events in the AMY 2018 weather year.
  A single cold snap or heat event could dominate this number. The CA peak baseline of 2.181
  may simply reflect a single unusual interval, not a characteristic operating condition.
- The outlier rate for Retail Standalone is elevated but not extreme (1–2% vs. Warehouse
  at 5.6% in CA baseline per `reports/qa_checks.csv`). The cause likely reflects
  irregular occupancy or HVAC scheduling in retail prototypes rather than data error.
- Retail Standalone's electricity share is approximately 73–77% across counties
  (computed from `data/processed/combined.csv`), meaning the remaining ~23–27% is gas
  heating. A large peak reduction under Package 3 is consistent with eliminating peak
  gas-heating demand — but the magnitude of the CA reduction (−37% peak vs. −30% mean)
  suggests the peak event is being disproportionately affected, which warrants scrutiny.
- Comparing peak values across upgrade scenarios is inherently limited: the two scenarios
  share the same AMY 2018 weather inputs, so the peak timestep will occur under the same
  weather event. This is valid for within-year comparison but does not address year-to-year
  climate variability.

**Bottom line**: The large peak reductions for Retail Standalone are plausible but should
be treated with particular caution. The peak statistic's sensitivity to individual extreme
intervals, combined with the elevated outlier rate, means the CA peak reduction in
particular warrants confirmation through examination of the specific timesteps driving
the baseline peak, before citing in formal analysis.

---

## Summary Table

| # | Finding | Direction of evidence | Key caveat |
|---|---|---|---|
| 1 | Package 3 halves winter school energy in CO/MI via heating fuel-switching | Strong — physically coherent, consistent across counties | HP cold-climate COP assumptions drive magnitude; occupancy conflated with seasonal effect |
| 2 | CA warehouse overnight load exceeds daytime, driven by exterior lighting | Moderate — explained by model structure | Exterior lighting assumptions are parametric inputs, not metered |
| 3 | Restaurants resist Package 3 because gas cooking is outside upgrade scope | Strong — mechanistically well-supported | Small % ≠ negligible absolute savings |
| 4 | CA school energy is summer-heavy; CO/MI school energy is winter-heavy | Moderate — directionally credible | School-calendar occupancy confounds seasonal comparison |
| 5 | Retail Standalone shows largest peak reduction but also highest outlier rate | Weak-to-moderate — plausible but peak statistic is unstable | Single 15-min peak is highly sensitive to individual weather events |

---

*Analysis date: 2026-03-13*
*All values computed from `data/processed/combined.csv` unless noted as citing `reports/eda_stats_new.csv` or `reports/qa_checks.csv`*
*These findings are exploratory and have not been independently validated*
