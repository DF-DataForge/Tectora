# Tectora Dakmeting — Odoo module

Native Odoo rewrite of the standalone Tectora/BROOF roof-measurement app.
Everything that Odoo already does well (customers, products, quotations,
invoicing, Belgian VAT) is delegated to the standard apps; this module adds
only the roofing-specific part: measuring flat roofs on a drawing canvas and
turning the measurement into a quotation.

## What replaced what

| Legacy standalone app | In Odoo |
|---|---|
| `projects` table + Express API | `tectora.roof.project` model |
| `roof_sections` / `roof_objects` | `tectora.roof.section` / `tectora.roof.object` |
| `section_products` (coverage + quantity) | `tectora.roof.section.product` |
| Custom `products` table | Standard `product.product` (Sales app) |
| Custom `sales_orders` + `order_line_items` | Standard `sale.order` (generated per section, with section headers) |
| Custom `invoices` + Belgian VAT engine (`shared/vat.ts`) | Standard `account.move`; VAT via Odoo taxes (`l10n_be`) |
| Odoo JSON-RPC bridge (`server/odoo-service.ts`) | Obsolete — the code *runs inside* Odoo |
| Fabric.js drawing canvas (React) | OWL field widget `roof_canvas` (vanilla canvas 2D, no external libs) |
| `server/satellite-service.ts` (Google/Mapbox) | Python methods on the project model; keys in Settings |
| Express sessions / no auth | Odoo users, groups & record rules |

## Installation

1. Copy (or symlink) `odoo/tectora_roof` into your Odoo addons path.
2. Update the app list and install **Tectora Dakmeting** (installs
   Sales/`sale_management` and CRM as dependencies).
3. For Belgian VAT, install the Belgian localization (`l10n_be`) so the
   21/12/6/0% taxes exist. Use a fiscal position for the 6% rate
   ("renovatie woning ouder dan 10 jaar").
4. Optional: in *Settings → Tectora Dakmeting*, set a **Google Maps API key**
   (Geocoding + Static Maps APIs) or a **Mapbox access token** to enable
   satellite backgrounds. Without a key you can still draw — upload a plan
   image manually and set the scale on the *Achtergrond & schaal* tab.

Requires Odoo **19.0**. Python dependencies (`requests`, `Pillow`) ship with
every standard Odoo install. The module uses the modern view syntax
(`<list>` views, the `<chatter/>` tag) and the Odoo 18+ product model
(`type`/`is_storable` instead of the removed `detailed_type`), so it does not
install on Odoo 17 or earlier without adjustments.

## Workflow

1. **Dakmeting → Dakprojecten → New**: name the project, pick the customer
   (address auto-fills) and optionally link a CRM opportunity.
2. Save, then click **Satellietbeeld ophalen**: the address is geocoded, a
   satellite photo is stored as drawing background and the geographic scale
   (m/pixel) is computed from the map projection.
3. On the **Tekening** tab, draw roof sections with the rectangle or polygon
   tool. Shapes show live real-world dimensions (m, m²). Select to move,
   double-click to rename, Delete to remove.
4. Click **Meting bijwerken uit tekening**: sections and roof objects are
   created/updated from the shapes (matched by canvas ID, so re-syncing after
   edits keeps assigned products).
5. On the **Daksecties** tab, open a section and add product lines. The
   quantity defaults from the coverage type: *surface* → area (m²),
   *edges* → perimeter (m), *corners* → 4, *drainage* → 1. A section can be
   converted into a chimney or skylight roof object from here.
6. Click **Offerte maken**: a standard quotation is created with one order
   section per roof section and the product lines beneath it. From there the
   normal Odoo flow applies: send, confirm, deliver, **invoice** — taxes,
   payment terms and the per-rate VAT breakdown come from the Invoicing app.

## Data model notes

- Shape coordinates are stored in image-pixel space in `canvas_data` (JSON in
  a Text field); the server recomputes area/perimeter with the shoelace
  formula using `scale_m_per_px`, so client and server always agree.
- `canvas_ref` links a section/object to its shape. Records created by hand
  (without a ref) are never touched or deleted by the canvas sync.
- Chimneys default to 1.5 m height; volume = area × height (same defaults as
  the legacy app).
- Google Static Maps images are fetched at zoom 20, 640×640 @2x; the scale
  accounts for the retina factor by measuring the actual stored image width.

## Projectdossier (Odoo Project integratie)

Elk dakproject krijgt een `project.project` dossier met een eigen analytische
rekening. Het dossier wordt aangemaakt zodra je een offerte genereert of op
**Projectdossier** klikt.

* De gegenereerde verkooporder krijgt `project_id`, waardoor Odoo de
  analytische distributie op elke orderlijn zet: omzet, facturen, inkoop-
  kosten en leveringen komen samen op de analytische rekening en in de
  winstgevendheidsrapportering van het project.
* Bij het **bevestigen** van een verkooporder wordt de **materiaallijst**
  opgebouwd: elk verkocht product wordt via zijn stuklijst (`mrp.bom`,
  inclusief geneste kit-stuklijsten) ontbonden in componenten; producten
  zonder stuklijst komen zelf als materiaal in de lijst. Diensten worden
  overgeslagen. Handmatig toegevoegde lijnen blijven bewaard; lijnen van een
  eerdere bevestiging van dezelfde order worden vervangen.
* Kerncijfers op het dakproject: **Omzet** (bevestigde orders),
  **Materiaalkost** (stuklijst x kostprijs) en **Marge**.
* Slimme knoppen: Offertes, Materialen, Leveringen, Inkoop, Facturen en het
  Projectdossier zelf.

Manufacturing (`mrp`) en Inkoop (`purchase`) zijn optioneel: zonder
Manufacturing bevat de materiaallijst de verkochte producten zelf, zonder
Inkoop blijft de inkoopknop leeg.

## Planning op ploegen

**Ploegen** (menu *Ploegen*) zijn vaste groepen medewerkers: eigen ploegleden,
of — als je die leeg laat — de medewerkers van een gekozen afdeling, telkens
samen met de ploegbaas. Zo blijft het model configureerbaar zonder de
HR-structuur te dupliceren.

Op een dakproject kies je een **ploeg** en de **geplande start/einde**. Zodra
beide ingevuld zijn, maakt het systeem automatisch een **werkblok**
(`tectora.roof.planning`) aan met alle leden van de ploeg. Een werkblok is het
planning-item van de werf: het toont de basisinformatie van het project
(referentie, klant, werfadres, projecttype, oppervlakte en omtrek) plus de
toegewezen medewerkers, en is te bekijken in kalender- of lijstweergave
(menu *Planning*).

* **Splitsen per dag** (knop op het werkblok of in de lijst) splitst een
  meerdaags blok in één blok per kalenderdag — dezelfde logica als het
  splitsen van een planning-shift. Elk resulterend blok krijgt een eigen kopie
  van de medewerkerslijst en kan daarna onafhankelijk herbezet worden.
* Bestaande werkblokken worden nooit overschreven: pas de ploeg of de data aan
  en gebruik **Planning aanmaken** voor een extra blok.

### Planning-app (optioneel)

Het aparte bridge-moduletje **tectora_roof_planning** installeert zichzelf
zodra zowel Dakmeting als de Odoo **Planning**-app aanwezig zijn. Dan wordt
elke toegewezen medewerker een echte planning-shift (`planning.slot`), zichtbaar
in de Planning-app en in de eigen planning van de medewerker. De shifts volgen
het werkblok: data, medewerkers en status worden gesynchroniseerd, splitsen
splitst de shifts mee en het verwijderen van een blok verwijdert zijn shifts.
Zonder de Planning-app blijven de werkblokken met hun medewerkerslijst gewoon
werken.
