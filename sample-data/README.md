# Sample Data Dictionary

This directory contains realistic ESG sample datasets for testing the CarbonBridge ingestion pipeline.
Each dataset includes a mix of **good records**, **bad records**, **unit inconsistencies**, and **missing values** to stress-test all adapter validation paths.

---

## SAP ERP Exports (`/sap/`)

All SAP files use **German column headers** and semicolon (`;`) delimiters, mirroring real SAP ERP exports.

### `fuel_purchases.csv`

| Column | SAP German Header | Description |
|---|---|---|
| `posting_date` | `Buchungsdatum` | Transaction posting date |
| `plant_code` | `Werk` | Plant/site identifier |
| `material_group` | `Materialgruppe` | Material group (maps to activity type) |
| `quantity` | `Menge` | Quantity with German decimal formatting (e.g. `1.200,50`) |
| `unit` | `Mengeneinheit` | Unit of measure |
| `document_type` | `Belegart` | SAP document type code |
| `document_number` | `Belegnummer` | SAP document number |
| `cost_centre` | `Kostenstelle` | Cost centre code |
| `amount` | `Betrag` | Monetary amount |
| `currency` | `Währung` | Currency code |

**Intentional bad records:**

| Row | Issue |
|---|---|
| Row 11 | Unit is `MWH` for a fuel (Diesel) — wrong unit family |
| Row 14 | Negative quantity (`-200,00`) — returns violation |
| Row 16 | Quantity and amount both blank — missing required field |
| Row 19 | Unit is blank — missing unit |
| Row 21 | Plant code and cost centre both blank — missing source reference |
| Row 22 | Future date (`2026-01-15`) — will be flagged as suspicious |

---

### `procurement_purchases.csv`

Same German headers. Material groups (`Verbrauchsmaterial`, `Rohstoff`, `Material`, `Waren`) map to `procurement` activity type.

**Intentional bad records:**

| Row | Issue |
|---|---|
| Row 7 | Unit is `LBS` (pounds) instead of `kg` — unit inconsistency requiring conversion |
| Row 13 | Negative quantity — returns violation |
| Row 14 | Quantity and amount both blank — missing required field |
| Row 17 | Unit is blank — missing unit |
| Row 19 | Unit is `G` (grams) — very small unit, triggers volume spike detection |
| Row 20 | Plant and cost centre both blank — missing source reference |
| Row 21 | Extremely large quantity (`9,999,999 kg`) — will trigger historical spike flag |

---

## Utility Portal Exports (`/utility/`)

### `electricity_bills.csv`

Uses **German field aliases** compatible with `UtilityAdapter` header mapping.

| Column | Description |
|---|---|
| `invoice_number` | Maps to `account_ref` |
| `meter_id` | Maps to `meter_id` |
| `standort` | Maps to `site` (German for "location") |
| `energietraeger` | Maps to `commodity` — value `Strom` (electricity) |
| `von` / `bis` | Maps to `period_start` / `period_end` (German for "from/to") |
| `zaehlerstand_anfang` | Opening meter reading |
| `zaehlerstand_ende` | Closing meter reading |
| `verbrauch` | Net consumption — maps to `consumption` |
| `einheit` | Unit — maps to `unit` (`kWh` or `MWh`) |
| `waehrung` | Currency |
| `preis` | Unit rate |
| `tarif` | Tariff code |

**Intentional bad records:**

| Row | Issue |
|---|---|
| Row 8 | Unit is `MWh` — requires conversion to `kWh` (×1000) |
| Row 12 | Opening and closing meter readings are blank |
| Row 13 | Unit (`einheit`) is blank — missing required field |
| Row 14 | `meter_id` and `tarif` are blank — missing source reference |
| Row 15 | Negative consumption (`-12700.00`) — suspicious flag |
| Row 16 | `period_start` is `2026-04-01` but `period_end` is `2025-03-31` — future date + inverted range |
| Row 19 | Consumption of `125,000 kWh` for an office — extreme spike vs. historical average |

---

### `gas_billing_periods.csv`

Natural gas (`Erdgas`) billing data. Unit mix exercises the adapter's calorific conversion logic.

| Column | Description |
|---|---|
| `rechnungsnummer` | Maps to `account_ref` (German for "invoice number") |
| `meternr` | Maps to `meter_id` |
| `energietraeger` | Maps to `commodity` — value `Erdgas` (natural gas) |
| `von` / `bis` | Billing period start / end |
| `verbrauch` | Net consumption |
| `einheit` | Unit: `m3` → converted to kWh @ 10.55; `CBM` alias for m³; `GJ` → 277.778 kWh |

**Intentional bad records:**

| Row | Issue |
|---|---|
| Row 7 | Unit is `CBM` — alias for m³, tests alias resolution |
| Row 9 | `meternr` and `tarifnummer` blank — missing source reference |
| Row 10 | Unit (`einheit`) blank — missing required field |
| Row 11 | Negative consumption — suspicious flag |
| Row 12 | Unit is `GJ` — requires conversion (1 GJ = 277.778 kWh) |
| Row 13 | `period_start` is `2026-04-01` (future) but `period_end` is `2025-03-31` — inverted range |
| Row 17 | Consumption of `88,500 m³` — massive spike vs. historical average, suspicious flag |



---

## Corporate Travel Exports (`/travel/`)

### `corporate_travel.json`

JSON array compatible with `TravelAdapter`. Contains **flights**, **hotels**, and **taxis/ground transport**.
Deliberately mixes field name aliases (e.g. `expense_type` vs `type`, `check_in_date` vs `date`, `origin_airport` vs `origin`) to test the adapter's alias resolution.

**Activity type coverage:**

| Type Key Used | Canonical Type | Records |
|---|---|---|
| `flight` | `flight` | 14 |
| `hotel` / `lodging` | `hotel` | 8 |
| `taxi` / `ground` | `ground_transport` | 7 |

**Intentional bad records:**

| Booking ID | Issue |
|---|---|
| `TRP-2025-0005` | No `origin` provided — adapter uses IATA lookup fallback only from destination |
| `TRP-2025-0012` | Missing `origin` — distance cannot be derived from IATA coords, falls back to 0 |
| `TRP-2025-0017` | Hotel `nights = -2` — negative value, triggers suspicious flag |
| `TRP-2025-0018` | Taxi with no distance fields — both `distance_km` and `distance_miles` missing |
| `TRP-2025-0021` | Date is `2099-06-01` — far future date, triggers suspicious flag |
| `TRP-2025-0023` | Hotel with no `nights` field — missing required field |

**Field alias stress tests:**

| Booking ID | Aliases Used |
|---|---|
| `TRP-2025-0019` | `expense_type`, `departure_date`, `employee_id`, `origin_airport`, `destination_airport`, `airline_code`, `flight_no`, `travel_class`, `km` |
| `TRP-2025-0020` | `expense_type`, `employee_id`, `property_name`, `city_name`, `country_code`, `room_nights` |

**Unit mix:**

| Booking ID | Distance Format |
|---|---|
| `TRP-2025-0004` | `distance_miles` |
| `TRP-2025-0016` | `distance_miles` |
| `TRP-2025-0024` | `distance_miles` |
| All others | `distance_km` |
