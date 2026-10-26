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
| **Titel- en tekstregels** | De regels in hoofdletters zonder aantal en prijs (ALGEMENE WERKEN, AFBOUWWERKEN THV HET PLAT DAK, COMMERCIËLE TEGEMOETKOMING, ...) worden **secties** van de offerte. Standaard: als secties, met de lijnen eronder ingedeeld (zie *Secties*); of overslaan. |
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

## Secties

De export levert de lijnen van een offerte **alfabetisch**: een sectietitel
staat niet meer boven zijn lijnen. De import zet elke lijn terug onder de
sectie waar ze het best bij past:

1. **Soort werk van de lijn**: korting / negatieve prijs → commerciële
   tegemoetkoming; ankerpunt, balustrade, stelling → veiligheid; vaste
   kosten, afval, transport, kraan, parkeervergunning → algemene werken;
   de categorie van de werkpost in de catalogus (01 algemeen, 02 veiligheid,
   03 afbraak); *Verwijderen …* → afbouwwerken; de rest → opbouwwerken.
2. **Een titel die de lijn noemt wint**: *AFBOUWWERKEN THV DE KOEPELS* voor
   "Verwijderen van de koepel", *DAMPSCHERM* voor het dampscherm,
   *AFVOER HEMELWATER* voor tapbuis en spuwer, ...
3. Anders de meest algemene titel van die soort; staat dezelfde lijn er
   meermaals (bv. een hoogste en een laagste plat dak), dan om beurten onder
   elk van die titels. Een lijn met aantal 0 komt onder de opties/varianten
   als de offerte die heeft.

De secties staan in de volgorde algemene werken, veiligheid, per dak afbouw
en opbouw (koepels als laatste), opties, commerciële tegemoetkoming, nota's.
Titels zonder lijnen (vaak *ALGEMENE NOTA'S*: de tekst van de nota zit niet
in de export) worden weggelaten; tekstregels komen onder de notasectie of
onderaan. Op de export van 26/10/2026 komen 47 van de 14 738 productlijnen
onder geen enkele sectie (bovenaan de offerte).

Dit is een zo goed mogelijke reconstructie: kijk een offerte na voor je ze
opnieuw verstuurt.

## Op de offerte

* Een lijn op een werkpost uit de catalogus wordt aangemaakt zoals Odoo dat
  zelf doet (naam en verkoopomschrijving van het product, zijn eenheid): de
  naam staat dus één keer op de offerte.
* De generieke **Werkpost (oud systeem)** is er per eenheid (m, m², stuk,
  forfait, ...), zodat er geen omrekening onder de hoeveelheid verschijnt. Het
  vinkje **Omschrijving als label** (productfiche, tab Algemeen) zorgt dat
  offertes, orders en facturen enkel de omschrijving van de lijn tonen, niet
  de productnaam erboven. Andere producten houden de standaardweergave van
  Odoo.

## Wat de import doet

* **Klanten**: gezocht op btw-nummer (genormaliseerd: `be 0723.806.575` =
  `BE0723806575`), dan op naam + postcode, anders aangemaakt (België). Een
  ongeldig btw-nummer komt in de notitie van de klant.
* **Lijnen**: een omschrijving die exact de naam van een werkpost
  (verkoopbare dienst) uit de catalogus is, krijgt dat product; de andere
  komen op de werkpost **Werkpost (oud systeem)** (`TECTORA-IMPORT…`, één
  per eenheid) met hun eigen omschrijving en eenheid. Korting, btw-tarief
  en **prijs komen uit de oude offerte** en worden door Odoo nooit herrekend
  (ook niet bij een gewijzigde hoeveelheid).
* **Vermenigvuldigde lijnen**: in de export is bij sommige lijnen het bedrag
  een veelvoud van aantal × prijs (het oude systeem vermenigvuldigde de lijn
  in een kolom die de export weglaat). Het bedrag is juist, dus het aantal
  krijgt die factor: zo klopt elk offertetotaal met de export.
* **Opmerkingen** (digitale ondertekening, ...) komen als interne notitie op
  de order; de *referentie klant* wordt de klantreferentie.
* Het resultaat toont per status het aantal orders, de nieuwe klanten, de
  gekoppelde en generieke lijnen, de gecorrigeerde lijnen en elke offerte
  die niet geïmporteerd kon worden (de rest gaat door).

## Projecten importeren

**Verkoop → Configuratie → Projecten importeren (oud systeem)**, *na* de
offertes: laad de projectenexport (`projecten_Tectora_BV_<datum>.xlsx`) op.
Ook hier eerst een **Testrun**: die toont welke projecten bij welke order
horen en op welke ploeg ze komen, zonder iets te wijzigen. De import zelf loopt
als importtaak op de achtergrond (*Offerte-imports*, soort *Projecten*).

* **Koppeling**: de export noemt geen offerte. Een project hoort bij de
  geïmporteerde order(s) van dezelfde klant (naam of btw-nummer) waarvan het
  totaal gelijk is aan *totaal offertes ex BTW* (tot drie orders samen; een
  bevestigde order gaat voor, een order hoort maar bij één project).
* **Dakproject en project** krijgen het projectnummer en de status van het
  oude systeem, het werfadres, de deadline (ook de leverdatum van de order) en
  de ploeg; een afgesloten project wordt *Afgerond*. Een bevestigde order zonder
  dakproject of project (de gefactureerde orders) krijgt ze nu. Een korte
  projectomschrijving komt in het project; de lange projectfiches kapt de
  export af (± 255 tekens, midden in de HTML) en worden niet overgenomen.
* **Ploeg**: de kolom *verantwoordelijke gebruiker* wordt een bestaande
  dakwerkersploeg via **Verkoop → Configuratie → Ploegen projectimport**. De
  import vult die tabel met zijn gok (de ploeg waarvan de naam erin staat:
  *TEAM 1 TECTORA: MARIUSZ & MARCIN* → Team 1, *DRENICA TEAM 2* → Drenica,
  *TEAM 1 + TEAM 2* → beide); verbeter hem daar en importeer opnieuw.
* **Inplannen**: een project met ploeg en deadline krijgt een werkblok op die
  ploeg dat op de deadline eindigt (07:30–16:30) en zoveel werkdagen duurt als
  de order geschat is (minstens 1). Afgesloten en uitgevoerde projecten
  (*afgesloten*, *Slotfactuur bezorgd…*, *Werk klaar…*) krijgen een blok
  *Uitgevoerd*, de andere *Ingepland*. Een project dat al werkblokken heeft,
  krijgt er geen bij.
* Opnieuw importeren koppelt niets dubbel: *Status bijwerken* neemt status,
  ploeg, deadline en adres opnieuw over.

Op de export van 26/10/2026: 221 projecten, waarvan 218 gekoppeld (2 met twee
orders). Niet gekoppeld: drie vervolgprojecten met totaal 0 (2026/0219,
2026/0096, 2026/0143). Twee projecten horen bij een offerte die *ON HOLD*
staat (2026/0196, 2026/0197): gekoppeld, maar zonder project tot de offerte
bevestigd wordt. Zonder ploeg (nog in te vullen): TM TOTALE RENOVATIE BV (24),
Tectora BV (21), DECLEIR DAKWERKEN (3), MIKO ROOF (2), Piotr Arne (1) en 5
projecten zonder verantwoordelijke.

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
