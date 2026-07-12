# SRF discovery — Phase 1 code and column reference

Open on demand at Phase 1 (see `static/core/workflow.md`). Contains the SRF API snippets
for vehicle metadata / organisation / capacity / date range, and the raw-telematics
column checklist. Step numbering (1.1 … 1.3) matches the core workflow's Phase 1.

## 1.1 Query SRF API for vehicle metadata

```python
import srf_client, requests, os, json
from dotenv import load_dotenv; load_dotenv()

srf = srf_client.SRFData(api_key=os.environ['SRF_API_KEY'],
                         root='https://data.csrf.ac.uk/api/')

# Search by registration (with space, e.g. "TA70 WTL")
vehicles = srf.vehicles.find_all(**{'registration': reg_with_space})
for v in srf_client.paging.paged_items(vehicles):
    print(v.registration, v.make, v.model, v.uri)
    # Key attributes available on Vehicle object:
    #   v.registration, v.make, v.model, v.vin, v.uri
    #   v.fuel_capacity  — nominal battery capacity (kWh), use as default nominal_kwh
    #   v.fuel, v.type, v.weight_class, v.country, v.description
    # NOTE: v.fleet does NOT exist — will raise AttributeError
```

## 1.1b Read organisation name (for company assignment)

`organisation` is NOT exposed on the Python `Vehicle` object. Use the REST API directly:

```python
headers = {'Authorization': f'Bearer {os.environ["SRF_API_KEY"]}'}
# v.uri gives the vehicle URL, e.g. "https://data.csrf.ac.uk/api/vehicles/177"
resp = requests.get(v.uri, headers=headers)
veh_json = resp.json()
org_url = veh_json.get('organisation', {}).get('_location', '')
if org_url:
    org_resp = requests.get(org_url, headers=headers)
    org_name = org_resp.json().get('name', '')
    # org_name examples: "JOLT Knowles-Volvo", "JOLT Nestle-Volvo", "JOLT Welch-Volvo",
    #                    "JOLT JLP-Volvo", "JOLT Partners", "Welch Group"
```

## 1.1c Auto-map organisation → company constant

Use the mapping below to convert SRF organisation names to plot_config company constants.
If no match found, present options to the user.

```python
ORG_TO_COMPANY = {
    'JOLT Knowles-Volvo': 'KNOWLES',
    'JOLT Nestle-Volvo': 'NESTLE',
    'JOLT Welch-Volvo': 'WELCH_TRANSPORT',
    'Welch Group': 'WELCH_TRANSPORT',
    'JOLT JLP-Volvo': 'JLP',
    'John Lewis Partnership': 'JLP',
    'JOLT Partners': None,  # Multi-operator — needs manual assignment
}
company = ORG_TO_COMPANY.get(org_name)
```

> **Note**: this mapping covers only KNOWLES / NESTLE / WELCH_TRANSPORT / JLP — other live
> companies (WJF, SJG, PORT_EXPRESS_DAIMLER, DP_WORLD, WS, …) fall through to the
> ask-the-user path, which is expected.

## 1.1d Nominal capacity from SRF

`v.fuel_capacity` returns the SRF-registered battery capacity in kWh.
Use this as the default `nominal_kwh` value. Present to user for confirmation only when
it differs significantly from known datasheet values.

> **Note**: SRF `fuelCapacity` may differ from datasheet nominal capacity for some vehicles
> (e.g., SRF shows usable capacity while datasheet shows gross capacity). Cross-reference
> against known vehicles: AV24LXJ SRF=265 vs config=360, N88GNW SRF=417 vs config=540.
> When discrepancy exists, prefer the value the user provides or the existing convention.

Present findings to user for verification (cross-check make/model with user's expectation).

## 1.2 Find available data date range

```python
import datetime, srf_client
params = {
    'start_time': srf_client.filter.between(
        datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
        datetime.datetime.now(datetime.timezone.utc)),
    'sort': srf_client.sort.asc('startTime'),
}
legs = srf.legs.find_all(**params, **{'trip.vehicle.registration': reg_with_space})
# Get first and last leg to determine data range
```

## 1.3 Inspect raw telematics data columns

Download 3-5 legs from different dates and inspect:

```python
import io, pandas as pd
for leg in sample_legs:
    raw = list(leg.get_raw_data())
    csv_text = "\n".join(c for c in raw if c.strip())
    df = pd.read_csv(io.StringIO(csv_text), dtype=str)
    print(f"Leg {leg.start_time.date()}: {len(df)} rows, cols: {list(df.columns)}")
```

**Key columns to identify:**

| Purpose | Common names | Check |
|---------|-------------|-------|
| Speed | `wheel_based_speed`, `speed` | Non-null count, range |
| SOC | `electricBatteryLevelPercent`, `state_of_charge` | Precision (integer vs float) |
| Odometer | `odometer`, `high_resolution_total_vehicle_distance` | Non-null |
| Mass | `gross_combination_vehicle_weight` | Non-null, range |
| Total energy | `total_electric_energy_used_plugged_in_included`, `total_electric_energy_used` | Availability |
| Moving energy | `electric_energy_wheelbased_speed_over_zero` | Availability |
| AC energy | `battery_pack_ac_watthours` | Availability |
| DC energy | `battery_pack_dc_watthours` | Availability |
| Altitude | `gnss_altitude` | Availability |
| Latitude/Longitude | `latitude`, `longitude` | Availability |

Present a data availability summary table to the user.
