# CarbonBridge — Sources & References

Standards, datasets, and external resources that informed the design and implementation of CarbonBridge.

---

## GHG Accounting Standards

| Source | Used For |
|---|---|
| [GHG Protocol Corporate Standard](https://ghgprotocol.org/corporate-standard) | Scope 1/2/3 categorisation logic; definition of direct vs. indirect emissions |
| [GHG Protocol Scope 3 Standard](https://ghgprotocol.org/scope-3-standard) | Scope 3 category mapping: Category 1 (procurement), Category 6 (business travel) |
| [ISO 14064-1:2018](https://www.iso.org/standard/66453.html) | Principles for quantification and reporting of GHG emissions at organisation level |
| [IPCC AR6 Annex II](https://www.ipcc.ch/report/ar6/wg1/) | GWP (Global Warming Potential) values referenced for CO₂e context |

---

## Emission Factor Databases (Referenced, Not Embedded)

| Source | Coverage |
|---|---|
| [DEFRA UK Government GHG Conversion Factors](https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting) | UK-specific EFs for fuel, electricity, freight, flights, hotels |
| [US EPA Emission Factors for GHG Inventories](https://www.epa.gov/climateleadership/ghg-emission-factors-hub) | US EFs for mobile combustion, stationary combustion, electricity |
| [IEA CO₂ Emissions from Fuel Combustion](https://www.iea.org/data-and-statistics) | Country-level electricity grid emission factors |
| [ecoinvent Database](https://ecoinvent.org/) | LCA-based EFs for materials and procurement (Scope 3 Cat. 1) |

> **Note:** Emission factors are intentionally not embedded in CarbonBridge. See `TRADEOFFS.md §2` for rationale.

---

## Unit Conversion Sources

| Conversion | Value Used | Source |
|---|---|---|
| US Gallon → Litres | 3.78541 L | [NIST Handbook 44](https://www.nist.gov/pml/weights-and-measures/publications/nist-handbooks/handbook-44) |
| Metric tonne → kg | 1,000 kg | SI definition |
| Pound (lb) → kg | 0.453592 kg | [NIST](https://www.nist.gov/pml/weights-and-measures) |
| MWh → kWh | 1,000 kWh | SI prefix definition |
| GJ → kWh | 277.778 kWh | SI: 1 GJ = 10⁶ kJ; 1 kWh = 3,600 kJ |
| Mile → km | 1.60934 km | [NIST](https://www.nist.gov/pml/weights-and-measures) |
| Gas m³ → kWh (calorific) | 10.55 kWh/m³ | [BEIS UK Standard Calorific Value](https://www.gov.uk/guidance/gas-meter-readings-and-bill-estimation) — gross calorific value for natural gas |
| EUR → USD | 1.08 | Approximate 2024 annual average (US Treasury / ECB) |
| INR → USD | 0.012 | Approximate 2024 annual average |

---

## Software & Libraries

| Library | Version | Purpose |
|---|---|---|
| [Django](https://www.djangoproject.com/) | 5.x | ORM, signals, admin, request handling |
| [Django REST Framework](https://www.django-rest-framework.org/) | 3.x | API serializers, authentication, views |
| [djangorestframework-simplejwt](https://django-rest-framework-simplejwt.readthedocs.io/) | 5.x | JWT-based access/refresh token auth |
| [React](https://react.dev/) | 19.x | Frontend UI framework |
| [react-router-dom](https://reactrouter.com/) | 7.x | Client-side routing |
| [recharts](https://recharts.org/) | 2.x | SVG-based chart components |
| [axios](https://axios-http.com/) | 1.x | HTTP client with interceptor support |
| [lucide-react](https://lucide.dev/) | latest | Icon set |
| [Vite](https://vitejs.dev/) | 8.x | Frontend build tool |

---

## SAP-Specific References

| Source | Used For |
|---|---|
| [SAP Help Portal — MB51 Material Document List](https://help.sap.com/docs/SAP_ERP/4c32b6b1a79b4ad3a82bec3e4e39b03a/4a2e90a33da51e13e10000000a42189c.html) | Understanding German SAP export column headers for material movement |
| [SAP MM Module Documentation](https://help.sap.com/docs/SAP_ERP/f88ab83d925b4efa8dbf2c0e40bff607/) | Material group (`Materialgruppe`) and unit of measure (`Mengeneinheit`) field semantics |
| [SAP CO3 / CO-PA Cost Centre Reports](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/) | Cost centre (`Kostenstelle`) field conventions |

---

## Corporate Travel References

| Source | Used For |
|---|---|
| [SAP Concur Developer Portal](https://developer.concur.com/api-reference/) | Concur JSON expense export field naming conventions (`expense_type`, `booking_id`, `cabin_class`) |
| [OpenFlights Airport Database](https://openflights.org/data.html) | Reference for IATA airport coordinate coverage (full dataset not embedded — see `TRADEOFFS.md §5`) |
| [IATA Resolution 787](https://www.iata.org/contentassets/7b3bab6e0a994df2b3e3f946e47f3a8f/) | Emission reporting methodology for passenger air travel (per-km, cabin-class weighting) |

---

## Utility / Energy References

| Source | Used For |
|---|---|
| [E.ON Energie Deutschland CSV Export Format](https://www.eon.de/de/pk/service/zaehlerstand.html) | Reference for German utility portal billing CSV column conventions (`von`, `bis`, `verbrauch`, `einheit`) |
| [Bundesnetzagentur UTILMD Standard](https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2021/BK6-21-197/BK6-21-197_Beschlusskammer_node.html) | EDIFACT UTILMD format for German meter data (referenced but not implemented — see `DECISIONS.md §2`) |
| [BEIS Gas Calorific Values](https://www.gov.uk/guidance/gas-meter-readings-and-bill-estimation) | Standard calorific value 10.55 kWh/m³ used for m³→kWh gas conversion |

---

## Multi-Tenancy Patterns

| Source | Used For |
|---|---|
| [Django Documentation — Custom Managers](https://docs.djangoproject.com/en/5.0/topics/db/managers/) | Implementation of `SoftDeleteManager` and tenant-scoped queryset |
| [Two Scoops of Django (Feldroy)](https://www.feldroy.com/books/two-scoops-of-django-3-x) | Fat models / thin views pattern; signal-based audit logging |
| [django-tenants (bernardopires)](https://github.com/django-tenants/django-tenants) | Reference for schema-per-tenant pattern (evaluated and rejected — see `DECISIONS.md §4`) |

---

## Audit Trail References

| Source | Used For |
|---|---|
| [GHG Protocol — Assurance Standard](https://ghgprotocol.org/ghg-protocol-corporate-accounting-and-reporting-standard) | Requirements for data completeness, accuracy, and traceability in ESG reporting |
| [Django Signals Documentation](https://docs.djangoproject.com/en/5.0/topics/signals/) | Implementation of `pre_save` / `post_save` audit hooks |
| [django-auditlog](https://github.com/jazzband/django-auditlog) | Reference implementation reviewed; custom solution chosen for tighter domain integration |
