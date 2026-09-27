# Odoo 19 → Odoo 20 upgrade notes

This folder holds the Tectora addons ported to **Odoo 20.0** (community
`odoo/odoo` branch `20.0`, Python 3.12+). The Odoo 19 modules at the
repository root are untouched. Every module version moved from `19.0.x.y.z`
to `20.0.x.y.z`, which is what makes Odoo 20 accept them as installable.

What changed, grouped by the Odoo 20 change that forced it.

## Access rights: `ir.access` replaces `ir.model.access` and `ir.rule`

Odoo 20 merges model access and record rules into one model, `ir.access`.
Every `security/ir.model.access.csv` became `security/ir.access.csv` with the
new columns `id,name,model_id,group_id/id,operation,domain`: the model by its
technical name, and the four `perm_*` flags as one `operation` string (`r`,
`crud`, …). The same record ids are kept. Every row has a group; a row
without a group would now be a *restriction* for everybody instead of a grant.

## Renamed and removed fields

| Where | Odoo 19 | Odoo 20 |
|---|---|---|
| `mrp.bom`, `mrp.bom.line` | `product_uom_id` | `uom_id` |
| `product.supplierinfo`, `purchase.order.line` | `product_uom_id` | `uom_id` |
| `stock.move` | `product_uom` | `uom_id` (and `name` is gone) |
| `uom.uom` | `rounding` | removed: every unit rounds on the "Product Unit" precision, through `uom.round()` / `compare()` / `is_zero()` |
| `res.partner` | `company_type` | removed: "is a company" follows from the VAT number |
| `ir.actions.report` | `report_file` | removed |

## Changed APIs

* `ir.config_parameter`: `get_param` / `set_param` are replaced by the typed
  `get_str`, `get_bool`, `get_int`, `get_float` (and `set_*`).
* `res.partner._display_address(without_company=…)` is now `without_name=…`.
* `product._select_seller()` returns the seller's data as a dict; the vendor
  pricelist line is under `"supplierinfo"`.
* `content_disposition` moved from `odoo.http` to `odoo.http.stream`.
* **Binary fields** read as a `BinaryValue` (raw bytes via `.content` or
  `.open()`, base64 via `.to_base64()`) instead of base64 bytes. Writing
  `bytes` raises: write a base64 `str`, a `BinaryValue` or
  `odoo.tools.binary.BinaryBytes(raw)`. `image_data_uri()` takes raw bytes
  too. Hence `tectora.roof.project._get_drawing_b64()` became
  `_get_drawing_png()` (raw PNG), the satellite image is stored as
  `BinaryBytes`, and the import wizards read their upload with `.open()`.
* `project._get_profitability_items()` is gone (Odoo 20 dropped the
  profitability panel for a single `real_cost`). The project dashboard now
  computes its four totals itself (`_tectora_profitability_totals`):
  invoiced and to-invoice from the order lines, billed from the costs on the
  project's analytic account, to-bill from the confirmed purchase lines charged
  to it, less what posted vendor bills cover, which is how Odoo 19 counted it.

## Views and templates

* **Sale order lines**: the list groups its fields in `<column>` elements, so
  hooks target `column[@name='price_unit']` / `column[@name='product_and_description']`.
* **Project kanban**: the card templates (and their menu) live in their own view,
  `project.view_project_card`; the "Dashboard" menu entry inherits that one.
* **QWeb `t-call`**: a `t-set` in the body of a `t-call` no longer reaches the
  called template. Parameters are attributes of the call
  (`<t t-call="…" white="True" title.translate="…"/>`). Twelve calls moved to
  that form.
* **`t-esc`** no longer exists on the server; `t-out` replaces it.
* **Portal home**: cards are `portal.entry` records now. "Mijn werven" is
  `data/portal_entry_data.xml`, counted through
  `_prepare_portal_counter_values` and shown to every employee through
  `portal.entry._filter_visible_portal_cards`.
* **Document layout**: layouts are built from shared parts
  (`web.company_address_list`, `web.external_layout_body`,
  `web.external_layout_footer_content`), and the table design is a company
  setting of its own (`report_tables_id`). The Tectora layout keeps its
  roof-edge header and colours on top of those parts; install and the
  `20.0.1.0.0` migration put companies on the default design on "Striped".
* **Icons**: Font Awesome is gone. Odoo 20 ships Material Symbols and
  `odoo_ui_icons` as `<i class="oi" data-icon="home"/>`, with
  `icon="home"` on buttons and `oi-fw` / `oi-spin` as modifiers. All
  113 icons were mapped, as were the dynamic ones (canvas toolbar and logistics
  routes).

## Client side: Owl 3

Odoo 20 runs **Owl 3**, without `useState`, `useRef` or static props:

* `static props = {…}` → `props = useProps({…})` with `t.*` types;
* `useState(…)` → `proxy(…)`;
* `useRef("x")` + `t-ref="x"` → `signal.ref()` + `t-ref="this.x"`, read as
  `this.x()`;
* templates render against `{this: component}`, so every component member
  in a template is written `this.…` (locals from `t-foreach` / `t-set` stay
  bare).

This applies to the roof canvas, its product picker and length dialogs, and
the product checklist.

## Verified

On a fresh Odoo 20.0 community database (all modules except
`tectora_roof_planning`):

* all modules install; **44 tests pass** (the existing suites, plus
  `tectora_purchase/tests/test_end_to_end.py` covering the whole flow and every
  document, and a portal check of the roof plan);
* the full flow: roof project → quotation → confirmation → material list,
  project and tasks → material delivery → purchase orders → invoice, and
  every report rendered (the quotation in its five styles and as a standard
  Odoo document, both roof sheets, the four logistics lists, purchase order,
  invoice, layout preview);
* in a browser, with no client errors: every Tectora action in every view type,
  the roof canvas (draw, select, product picker, side-length dialog, apply),
  the sale order's custom bill of materials dialog, and the employee portal
  (home, sites, every tab of a site).

## Not verified

* **`tectora_roof_planning`** depends on the Enterprise `planning` app, which
  is not available here. It got the same mechanical changes (version, config
  parameters, icons) and shows none of the patterns above, but its
  `planning.slot` fields, its gantt views and the `web_gantt` renderer it
  extends still need a run on Odoo 20 Enterprise.
* **PDF output** through wkhtmltopdf: the reports were rendered as HTML only.
* **Upgrading an existing Odoo 19 database** (through Odoo's upgrade
  service). The module migrations are in place, but no real database was
  migrated.
