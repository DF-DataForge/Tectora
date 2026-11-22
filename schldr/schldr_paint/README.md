# Data Forge Schldr

De toepassing: een schilderproject met zijn plan, zijn verfsystemen, zijn
offerte en zijn project.

## Werkwijze

1. **Schilderproject** aanmaken (menu *Schldr → Schilderprojecten*), vanuit een
   opportuniteit, of automatisch: elke offerte krijgt er één.
2. Op het tabblad **Plan** de ruimtes tekenen (*Tekenmodus* zet het plan
   schermvullend):
   * **Rechthoek**: sleep, of vul breedte en diepte in en klik.
   * **Vorm**: klik de hoeken; wijs een richting aan, typ een lengte en druk
     Enter. Lijnen lopen recht of onder 45° (Shift laat ze vrij).
   * **Deur**, **Raam**, **Radiator**: klik op een muur. De standaardmaten
     komen uit *Schldr → Deuren, ramen en radiatoren*.
   * **Schuin plafond**: klik op de muur waar het begint; kniehoogte en helling
     staan in het paneel.
   * Een muur aanklikken toont haar lengte (aanpasbaar: wat erachter ligt
     schuift mee), *geen muur* (open naar de ruimte ernaast) en *eigen hoogte*
     (trapgat). Dubbelklik op een muur maakt een extra hoek.
   * **+ verdieping** en **+ kopie** (dezelfde ruimtes als de verdieping eronder).
3. Onder **Standaard** per soort oppervlak (muren, plafonds, vloeren, houtwerk,
   objecten) één keer het verfsysteem en de kleur kiezen. Elk oppervlak volgt
   dat, tot je er met de **Kwast** of in het paneel iets anders op zet
   (*Niet schilderen* kan ook).
4. Het paneel **Offerte** toont wat het plan oplevert: per ruimte de werkposten
   met hoeveelheid en bedrag, en de verf per product en kleur in potten.
   **3D** toont de ruimtes met hun kleuren.
5. **Offerte maken** zet dat op een offerte: een sectie per ruimte (of één lijn
   per verfsysteem, zie tabblad *Offerte*), de algemene werken en de nota's.
6. **Order bevestigen** maakt het project met zijn taken *Voorbereiding* en
   *Schilderwerken* (uren uit de verfsystemen) en de **materiaallijst**.

## Wat gemeten wordt

| Oppervlak | Maat |
|---|---|
| Muur | lengte × hoogte (onder een schuin plafond: de werkelijke vorm), min de openingen, plus de dagkanten |
| Plafond, schuin plafond | het vlakke deel; elk schuin vlak op zijn werkelijke oppervlakte |
| Vloer | oppervlakte van de ruimte |
| Plinten | muurlengte min de deuropeningen |
| Kroonlijst | muurlengte |
| Omlijsting | lengte rond de deur of het raam |
| Deurblad | breedte × hoogte × twee zijden |
| Radiator | breedte × hoogte × factor |
| Vrij element | wat je ingeeft (lengte of oppervlakte) |

*Instellingen → Schldr → Openingen aftrekken vanaf*: een opening kleiner dan
die oppervlakte blijft in wat aangerekend wordt. De verf wordt altijd zonder
de openingen berekend.

## Verfsystemen

Een verfsysteem (*Schldr → Verfsystemen*) is wat je op een oppervlak doet en
als één werkpost verkoopt:

* de **werkpost** (een dienst met prijs), verkocht per m², per meter of per stuk;
* de **lagen**: grondlaag, tussenlaag, eindlaag, elk met product, aantal lagen,
  rendement (m² per liter), verdunning, verlies en uren per laag;
* **uren voorbereiding** per eenheid.

De uren van het systeem worden de tijdsnormen van de werkpost, zodat elke
offertelijn haar geschatte tijd kent. De verf staat niet op de offerte: bij
bevestiging komt ze op de materiaallijst, per product en **kleur** opgeteld
over het hele project en afgerond naar de **verpakkingen** van het product
(tabblad van het product). Staat er op elke verpakking een prijs, dan wordt de
goedkoopste combinatie gekozen.

## Offerte en plan

* Een offerte volgt het plan enkel als *Offerte volgt de meting* aanstaat, of
  wanneer je *Offerte bijwerken uit meting* klikt.
* Een lijn die al op de offerte staat, houdt haar prijs, korting en btw: enkel
  de hoeveelheid volgt. Lijnen die je zelf toevoegde blijven staan.
* *Zet offerte vast* houdt het plan van de offerte af.

## Technisch

* Het plan is één JSON-document (`schldr.project.canvas_data`, millimeters,
  vaste id's per muur, opening en ruimte; zie `lib/document.py`). Ruimtes,
  oppervlakken en toewijzingen (`schldr.room`, `schldr.surface`,
  `schldr.assignment`) zijn er een spiegel van, opgebouwd door
  `action_sync_from_canvas`.
* `lib/` (Python) en `static/src/plan_editor/lib/` (JavaScript) rekenen
  hetzelfde uit; `tests/fixtures` in de repository houdt ze gelijk.
* De editor is het veldwidget `schldr_plan` (`static/src/plan_editor/`):
  `plan_editor.js` (bediening), `plan_view.js` (tekenen en aanwijzen),
  `plan_3d.js` + `lib/scene3d.js` (3D), `lib/edit.js` (elke bewerking van het
  document, zonder browser te testen).
