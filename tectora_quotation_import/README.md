# Data Forge Dakmeting — Offerte-import

Importeert de offertes van het oude systeem (Simpla-export
`offertes_Tectora_BV_<datum>.xlsx`, tabblad *Export Simpla*) als
**verkooporders met hun verkoopkans**, in de staat en fase die bij hun status
horen. Gemaakt om bij elke nieuwe export opnieuw te draaien, eerst op staging,
later op live.

## Gebruik

**Verkoop → Configuratie → Offertes importeren (oud systeem)**: laad de
export op en klik *Importeren / controleren*.

* Met **Testrun** aangevinkt wordt het bestand enkel gecontroleerd: je ziet
  hoeveel offertes er nieuw zijn (per status, met de orderstatus en fase die
  ze krijgen), hoeveel al in Odoo staan, hoeveel klanten nieuw zijn en hoeveel
  lijnen op een werkpost uit de catalogus komen. Er wordt niets aangemaakt.
* Zonder testrun wordt een **importtaak** gestart die op de achtergrond loopt
  (geplande actie *Offerte-import oud systeem*). Elke offerte wordt apart
  bewaard, zodat een grote export nooit tegen de tijdslimiet van de server
  botst; wordt de import onderbroken, dan gaat hij verder waar hij stond.
  Volg hem in **Verkoop → Configuratie → Offerte-imports** (voortgang,
  resultaat, *Stoppen* / *Verdergaan*, knop naar de geïmporteerde orders).

| Optie | Betekenis |
|---|---|
| **Gekende offertes** | Een offerte waarvan het nummer al in Odoo staat, wordt nooit opnieuw aangemaakt. *Status bijwerken* (standaard) brengt een offerte die intussen goedgekeurd werd naar een bevestigde order en haar verkoopkans naar gewonnen. Lijnen worden niet aangeraakt, een bevestigde order gaat nooit terug. *Overslaan* laat gekende offertes ongemoeid. |
| **Offertenummer als ordernummer** | De order heet zoals in het oude systeem (bv. `2026/0004`). Het oude nummer staat sowieso op de order (*Offertenummer oud systeem*, zoekbaar, filter *Uit oud systeem*). |
| **Titel- en tekstregels** | Regels zonder aantal, prijs en bedrag (ALGEMENE WERKEN, OPBOUWWERKEN THV HET PLAT DAK, ALGEMENE NOTA'S, ...). De export levert de lijnen **alfabetisch**, dus een titel staat niet meer boven zijn lijnen: standaard overgeslagen, of als notitie onderaan de offerte. |
| **Verkoper / Verkoopteam** | Op de orders en verkoopkansen (de export bevat geen verkoper). |
| **Btw 0% / 6% / 21%** | Standaard de dienstenvariant van de Belgische btw (`6% S`, `21% S`) en `0% Cocont` (medecontractant) voor 0%. |

## Status → order en verkoopkans

Instelbaar in **Verkoop → Configuratie → Statussen oud systeem**. Een status
in het bestand die daar niet staat, stopt de import vóór er iets geschreven
wordt.

| Status oud systeem | Verkooporder | Verkoopkans | Dakproject / project | Facturatie |
|---|---|---|---|---|
| openstaand | offerte verzonden | Lopende offerte | ja | — |
| ON HOLD | offerte verzonden | Lopende offerte | ja | — |
| niet goedgekeurd | offerte verzonden | Lopende offerte | ja | — |
| goedgekeurd | bevestigde order | Gewonnen | ja | te factureren |
| deels gefactureerd | bevestigde order | Gewonnen | ja | te factureren (rest in Odoo) |
| gefactureerd | bevestigde order | Gewonnen | nee | gefactureerd (facturen in oud systeem) |

* De fasen zijn de standaardfasen van Odoo die bij Tectora hernoemd zijn:
  *Lopende offerte* (`crm.stage_lead3`) en *Gewonnen* (`crm.stage_lead4`).
  Per status kan een andere fase vast gekozen worden; ontbreken die fasen,
  dan wordt op naam gezocht.
* Een bevestigde order krijgt, zoals een bevestiging in Odoo, het plannebare
  project met zijn dashboard; voor volledig gefactureerde (afgewerkte) werven
  wordt geen dakproject of project gemaakt.
* Een volledig gefactureerde order telt in Odoo als **gefactureerd** en
  verschijnt niet bij *Te factureren*. Een deels gefactureerde blijft te
  factureren voor het volle bedrag: het reeds gefactureerde deel staat in het
  oude systeem.
* De orderdatum blijft de offertedatum (ook na bevestiging), de
  vervaldatum is offertedatum + geldigheidstermijn; de gewonnen verkoopkans
  krijgt de offertedatum als sluitingsdatum.

## Wat de import doet

* **Klanten**: gezocht op btw-nummer (genormaliseerd: `be 0723.806.575` =
  `BE0723806575`), dan op naam + postcode, anders aangemaakt (België). Een
  ongeldig btw-nummer komt in de notitie van de klant.
* **Lijnen**: een omschrijving die exact de naam van een werkpost
  (verkoopbare dienst) uit de catalogus is, krijgt dat product; de andere
  komen op de werkpost **Werkpost (oud systeem)** (`TECTORA-IMPORT`) met hun
  eigen omschrijving. Eenheid, korting, btw-tarief en **prijs komen uit de
  oude offerte** en worden door Odoo nooit herrekend (ook niet bij een
  gewijzigde hoeveelheid).
* **Vermenigvuldigde lijnen**: in de export is bij sommige lijnen het bedrag
  een veelvoud van aantal × prijs (het oude systeem vermenigvuldigde de lijn
  in een kolom die de export weglaat). Het bedrag is juist, dus het aantal
  krijgt die factor: zo klopt elk offertetotaal met de export.
* **Opmerkingen** (digitale ondertekening, ...) komen als interne notitie op
  de order; de *referentie klant* wordt de klantreferentie.
* Het resultaat toont per status het aantal orders, de nieuwe klanten, de
  gekoppelde en generieke lijnen, de gecorrigeerde lijnen en elke offerte
  die niet geïmporteerd kon worden (de rest gaat door).

## De export van 26/10/2026

`offertes_Tectora_BV_26_10_2026.xlsx`: 585 offertes, 18 187 lijnen
(14 709 product- en 3 478 titel/tekstregels), € 10 212 256,17 excl. btw.

| Status | Offertes |
|---|---|
| niet goedgekeurd | 256 |
| gefactureerd | 179 |
| openstaand | 75 |
| deels gefactureerd | 38 |
| ON HOLD | 29 |
| goedgekeurd | 8 |

Dus 360 lopende offertes en 225 bevestigde orders. 292 lijnen zijn
vermenigvuldigd (factor 2 tot 5); daarna sluiten alle 585 offertetotalen op
de cent aan bij de export. Ongeveer 68% van de productlijnen heeft een naam
die exact een werkpost uit de catalogus is.
