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
   image through the globe icon on the drawing and calibrate the scale by
   right-clicking a side's length label.

Requires Odoo **19.0**. Python dependencies (`requests`, `Pillow`) ship with
every standard Odoo install. The module uses the modern view syntax
(`<list>` views, the `<chatter/>` tag) and the Odoo 18+ product model
(`type`/`is_storable` instead of the removed `detailed_type`), so it does not
install on Odoo 17 or earlier without adjustments.

## Workflow

1. **Dakmeting → Dakprojecten → New**: name the project, pick the customer
   (address auto-fills) and optionally link a CRM opportunity.
2. On the **Tekening** tab, open the globe icon and choose **Satellietbeeld
   ophalen**: the project is saved, the address is geocoded, a satellite
   photo is stored as drawing background and the geographic scale (m/pixel)
   is computed from the map projection. The same menu uploads your own plan,
   shows/hides the background, sets its transparency and removes it.
3. On the **Tekening** tab, draw roof sections with the rectangle or polygon
   tool. Shapes show live real-world dimensions (m, m²). Select to move,
   double-click to rename, Delete to remove.
   A **naad** (seam) marks that two roof surfaces are separate: draw it with
   the *Naad* tool as an open dotted line (click points, double-click to
   finish). It is stored as a roof object of type *Naad* with its length;
   clicking its label assigns products from categories whose *Kan gebruikt
   worden voor* includes **Naden**, measured by the seam length.
4. Click **Meting bijwerken uit tekening**: sections and roof objects are
   created/updated from the shapes (matched by canvas ID, so re-syncing after
   edits keeps assigned products).
5. On the **Daksecties** tab, open a section and add product lines. The
   quantity defaults from the coverage type: *surface* → area (m²),
   *edges* → perimeter (m), *corners* → 4, *drainage* → 1. A section can be
   converted into a chimney or skylight roof object from here.
6. Click **Offerte maken**: a standard quotation is created with one order
   section per roof section and the product lines beneath it (or start from
   Sales: a quotation created there gets its own roof project). From there
   the normal Odoo flow applies: send, confirm, deliver, **invoice** — taxes,
   payment terms and the per-rate VAT breakdown come from the Invoicing app.
7. **Confirming** the order creates the plannable project; click it (Project
   app or *Dakmeting → Projecten*) for the dashboard with revenue and costs,
   deliveries, tasks and team planning.

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

## Dakproject ↔ verkooporder (1 op 1)

Eén dakproject staat tegenover één offerte/order, in beide richtingen:

* Een **verkooporder die rechtstreeks aangemaakt wordt** (Verkoop → Offertes)
  krijgt automatisch een dakproject (zonder meting) met de klant, het
  leveradres als werfadres, de opportuniteit, de verkoper en het projecttype
  dat uit de prijslijst volgt. De smart button **Dakproject** op de order
  opent het; wie liever eerst tekent, maakt het dakproject en klikt daar op
  **Offerte maken**.
* Een offerte kan dus vanuit de **standaard verkooporder** of vanuit het
  **dakproject** opgemaakt worden. Zolang de offerte open staat vervangt
  **Offerte bijwerken uit meting** haar lijnen door de meting; een bevestigde
  order wordt niet meer overschreven. Een geannuleerde order blijft in de
  historiek (**Offertes / Orders**) en maakt plaats voor een nieuwe.
* Klant, opportuniteit, verkoper ↔ projectleider, leverdatum ↔ deadline en
  prijslijst ↔ projecttype blijven **gesynchroniseerd**: wat je op de ene kant
  wijzigt, verschijnt op de andere. Klant en prijslijst worden alleen nog op
  een openstaande offerte aangepast, niet meer op een bevestigde order. Het
  veld **Offerte / Order** op het dakproject (of **Dakproject** op de order)
  koppelt een bestaand record; de andere kant vult dan de ontbrekende gegevens
  aan.
* Bij het bevestigen van de order gaat het dakproject naar **Order bevestigd**;
  annuleren zet het terug op *Offerte gemaakt*.

Elke order zonder dakproject krijgt er een bij het aanmaken; wie dat voor een
technische import niet wil, geeft de context `tectora_no_roof_project` mee.

### Offerte volgt de meting (spiegeling)

De offerte en het dakproject spiegelen elkaar, zolang de offerte open staat:

* De **hoofdstuktabs** op het dakproject zijn de projectlijnen; elke regel
  staat als lijn onder het overeenkomstige hoofdstuk van de offerte.
  *Algemene werken* en *Veiligheid* tonen de volledige checklist van het
  hoofdstuk om aan te vinken; *Afbraak*, *Opbouw* en *Overige* tonen alleen
  de producten die op de offerte staan, met een regel *Toevoegen* die enkel
  producten van dat hoofdstuk aanbiedt.
  Omgekeerd wordt elke offertelijn (ook uit een offertesjabloon of handmatig
  toegevoegd) een projectlijn op het dakproject, in de tab van haar
  productcategorie.
* **Hoeveelheden volgen de meting**: een m²-product neemt de dakoppervlakte,
  een m-product de omtrek (uit de tekening); getelde producten (stuks, forfait,
  dagen) nemen het aantal van de offerte over en zijn op beide kanten te
  wijzigen. Op een daksectie of dakobject volgt een oppervlakteproduct de
  oppervlakte en een randproduct de omtrek van die vorm.
* De **meetlijnen** (per daksectie en dakobject, uit het tekenen en de
  productkiezer) worden bij elke wijziging van de tekening herbouwd op de
  offerte, onder een kop per daksectie. Een projectlijn voor een product dat
  de tekening intussen zelf prijst, valt weg zodat niets dubbel telt.
* Lijnen die je zelf op de offerte toevoegt voor een product dat de meting al
  prijst, worden met rust gelaten; een lijn verwijderen op de offerte
  verwijdert de projectlijn, en omgekeerd.

**Offerte bijwerken uit meting** brengt een open offerte handmatig in lijn;
een bevestigde order wordt nooit meer aangepast. De tab **Werf** (voorheen
*Projectinformatie*) bundelt de werfvoorbereiding.

## Project (Odoo Project) en projectdashboard

Bij het **bevestigen** van de order wordt een planbaar **project**
(`project.project`) aangemaakt, genoemd naar de klant en de gemeente van de
werf (*Data Forge — Wortegem*), met een eigen analytische rekening — of het
project dat Odoo zelf al maakte voor diensten met projectopvolging wordt
overgenomen. Dit project is de basis van de **nacalculatie**: de order krijgt
het als `project_id` (zodat Odoo de analytische distributie op elke orderlijn
zet) en het project wijst terug naar de order, zodat omzet, facturen,
inkoopkosten, leveringen en urenstaten er samenkomen en Odoo's eigen
winstgevendheidsrapport het oppikt.

Klikken op een project — in de Project-app of via *Dakmeting → Projecten* —
opent het **projectdashboard**. De kaarten zijn doorklikbaar naar de
achterliggende records:

* **Omzet** (bevestigde order excl. btw, gefactureerd / te factureren),
  **Kosten** (alles op de analytische rekening: aankopen, leveranciersfacturen,
  urenstaten, voorraad; geboekt / verwacht) en **Marge** openen de
  winstgevendheidsanalyse van het project;
* **Materiaalkost** (stuklijst × kostprijs), **Inkoop**, **Urenstaten**
  (uren en loonkost; met de app Urenstaten), **Facturen** (met openstaand
  bedrag) en **Leveringen** (te leveren / deels geleverd / geleverd) openen de
  lijsten erachter;
* **Taken** (open / afgerond) en **Planning** (volgende werkdag, ploeg,
  geplande uren en de ingeplande medewerkers) openen de taken en de
  planning.

De smart buttons **Offerte / Order** en **Dakproject** zijn er altijd — ook
op een project dat nog geen van beide heeft: dan maken ze het aan. De tab
**Dakmeting** toont de meting zelf (tekening, oppervlakte, omtrek, daksecties),
de tabs **Planning**, **Taken** en **Materiaallijst** de details; met de
Planning-app (bridge `tectora_roof_planning`) staan ook de shifts van de
medewerkers op de tab Planning en opent de planningkaart de resourceplanner.
Het standaard projectformulier blijft bereikbaar via **Projectinstellingen**
en krijgt zelf de smart buttons Projectdashboard, Offerte / Order en
Dakproject.

Klant, projectleider en de geplande periode van het dakproject volgen naar het
project (start- en einddatum) en omgekeerd.

* Bij het **bevestigen** van een verkooporder wordt ook de **materiaallijst**
  opgebouwd: elk verkocht product wordt via zijn stuklijst (`mrp.bom`,
  inclusief geneste kit-stuklijsten) ontbonden in componenten; producten
  zonder stuklijst komen zelf als materiaal in de lijst. Diensten worden
  overgeslagen. Handmatig toegevoegde lijnen blijven bewaard; lijnen van een
  eerdere bevestiging van dezelfde order worden vervangen.
* Kerncijfers op het dakproject: **Omzet** (bevestigde orders),
  **Materiaalkost** (stuklijst x kostprijs) en **Marge**.
* Slimme knoppen op het dakproject: Offerte / Order, Materialen, Leveringen,
  Inkoop, Facturen, Werkblokken en het Project (dashboard).

Manufacturing (`mrp`), Inkoop (`purchase`), Voorraad (`stock`) en Urenstaten
(`hr_timesheet`) zijn optioneel: zonder Manufacturing bevat de materiaallijst
de verkochte producten zelf, zonder Inkoop/Voorraad/Urenstaten blijven de
overeenkomstige kaarten leeg.

## Planning op ploegen

**Ploegen** zijn vaste groepen medewerkers. De ploeg wordt op de
**werknemer** ingesteld: *Werknemers → werknemersfiche → tab Werk → Ploeg*
(één ploeg per medewerker), en de ploegen zelf staan onder *Werknemers →
Configuratie → Ploegen* (met de Planning-app ook onder *Planning →
Configuratie*). De Werknemers-app opent **per ploeg**: één kolom per ploeg,
ook lege, zodat medewerkers naar hun ploeg gesleept kunnen worden; wie geen
ploeg heeft staat in een eigen kolom. Filters *In een ploeg* en *Ploegbazen*
en een groepering *Ploeg* staan in het zoekvenster; de fiche toont ook de
ploegbaas. Een ploeg zonder eigen leden gebruikt de medewerkers van een
gekozen afdeling, telkens samen met de ploegbaas. Zo blijft het model
configureerbaar zonder de HR-structuur te dupliceren.

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
in de Planning-app en in de eigen planning van de medewerker. De planner
**Per ploeg** (de standaardweergave van de Planning-app, en de knop Planning
op dakproject en projectdashboard) toont per ploeg één **projectblok** per
werkblok met projectnaam en werfadres, niet de losse medewerkers. Verplaats of
verleng het blok en alle shifts volgen; klik erop voor de samenvatting met de
ingeplande medewerkers (verwijder er een om zijn shift eruit te halen) en de
knoppen **Projectoverzicht**, **Dakproject** en **Per medewerker**. De shifts volgen
het werkblok: data, medewerkers en status worden gesynchroniseerd, splitsen
splitst de shifts mee en het verwijderen van een blok verwijdert zijn shifts.
Zonder de Planning-app blijven de werkblokken met hun medewerkerslijst gewoon
werken.
