# Tectora

Odoo 19 addons for Tectora, flat-roof measurement and quoting for roofing
contractors.

## Modules

| Module | Description |
|---|---|
| [`tectora_roof`](tectora_roof/) | Tectora Dakmeting — draw and measure flat roofs on a satellite photo, assign products per coverage type and generate a quotation from the measurement. |

The application originates from the standalone BROOF app
(React + Express + PostgreSQL), which was rewritten as a native Odoo module
and then migrated to Odoo 19. Customers, products, quotations, invoicing and
Belgian VAT are handled by the standard Odoo Sales/Invoicing apps.

## Installation

1. Clone this repository and add it to your Odoo `addons_path` (or copy
   `tectora_roof/` into an existing addons directory).
2. Update the app list and install **Tectora Dakmeting**
   (`sale_management` and `crm` are installed as dependencies).
3. For Belgian VAT, install the Belgian localization (`l10n_be`).
4. Optional: in *Settings → Tectora Dakmeting*, set a Google Maps API key or
   a Mapbox access token to enable satellite backgrounds.

Requires **Odoo 19.0**. See [`tectora_roof/README.md`](tectora_roof/README.md)
for the full workflow and data-model notes.
