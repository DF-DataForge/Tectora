# Data Forge Stuklijst op maat

Pas de **stuklijst van een orderlijn** aan op de offerte zelf en bewaar ze,
als je wil, als **standaardstuklijst** van het product. Installeert zichzelf
zodra Dakmeting (`tectora_roof`) en Stuklijsten (`tectora_boms`) aanwezig zijn.

## Op de offerte

Elke productlijn heeft een knop met een lijstje (naast het product). Die opent
de stuklijst van de lijn:

* de eerste keer gevuld met de componenten van de **standaardstuklijst van het
  product** (dezelfde die de materiaallijst gebruikt), of leeg als het product
  er geen heeft; er wordt niets bewaard tot je op **Opslaan** klikt;
* hoeveelheden **per eenheid van het verkochte product** (per m², per m), of
  **Vast** voor de hele lijn (één container per werf, wat de oppervlakte ook
  is); de kolom *Totaal* toont wat de lijn nodig heeft;
* per component een **kostprijs** (standaard de kostprijs van het product, aan
  te passen) en de kost; bovenaan de **kostprijs per eenheid**, een **marge**
  en de **berekende prijs**. Bij het openen staat de marge zo dat de berekende
  prijs gelijk is aan de huidige prijs van de lijn.

Knoppen onderaan:

| Knop | Wat |
|---|---|
| **Opslaan** | bewaart de componenten; de prijs van de lijn blijft. |
| **Opslaan en prijs toepassen** | ook de berekende prijs komt op de orderlijn (alleen zichtbaar wanneer ze verschilt). |
| **Opslaan als standaardstuklijst** | de componenten worden de standaardstuklijst van het product: elke volgende offerte vertrekt ervan (beheerders Productie). |
| **Standaard herstellen** | de aanpassing verdwijnt; de lijn gebruikt weer de stuklijst van het product. |

*Berekende prijs als verkoopprijs product* (verkoopbeheerders) zet de berekende
prijs als verkoopprijs op het product.

Een lijn met een eigen stuklijst toont de knop in kleur. Bij het dupliceren van
een offerte gaat de stuklijst op maat mee.

## Materiaallijst

De stuklijst op maat **vervangt die van het product** wanneer de materiaallijst
van de order gebouwd wordt (bij bevestigen). Een component die zelf een kit
is, wordt opengeklapt zoals in de stuklijst van het product.

Op een **bevestigde** order volgt de materiaallijst elke wijziging meteen. Wat
al op een levering staat, blijft daar; *Levering klaarzetten*
(`tectora_roof_stock`) levert daarna het verschil.

## Opslaan als standaard

De stuklijst die de materiaallijst van een product gebruikt, is de eerste in
volgorde (een stuklijst voor een variant gaat voor die van het sjabloon).

* De meegeleverde stuklijsten van `tectora_boms` (de export en de demoset)
  worden bij elke upgrade opnieuw geladen via hun importsleutel. Ze worden dus
  **nooit overschreven**: er komt een nieuwe stuklijst met referentie
  **Op maat** vóór (volgorde één lager).
* Een stuklijst zonder importsleutel (met de hand gemaakt, of hier eerder
  opgeslagen) wordt **ter plaatse bijgewerkt**, zodat er niet bij elke keer
  een nieuwe bijkomt.

De stuklijst wordt opgeslagen voor 1 eenheid van het product; het vinkje
**Vast** staat ook op de stuklijstlijnen (*Productie → Stuklijsten*, kolom
*Vast*) en telt ook daar mee in de materiaallijst.

## Technisch

* `tectora.sale.bom` (één per orderlijn, `sale_line_id` uniek) en
  `tectora.sale.bom.line` (component, hoeveelheid per eenheid in de eenheid
  van het product, `fixed_quantity`, `unit_cost`).
* `sale.order.line`: `tectora_sale_bom_ids` (gekopieerd met de lijn),
  `tectora_sale_bom_id`, `tectora_has_sale_bom`,
  `action_open_tectora_sale_bom()`.
* `mrp.bom.line.tectora_fixed_qty`.
* `sale.order`: overschrijft de haken `_tectora_line_material_values` en
  `_tectora_exploded_quantity` van `tectora_roof`.

## Herkomst

Overgezet van `df_custom_bom_in_so` (Odoo 18) naar Odoo 19 en de Tectora-flow, en daarna naar Odoo 20.
Wat bewust anders is:

* geen herschrijven van leveringsregels bij bevestigen: Tectora bouwt een
  materiaallijst en maakt daaruit de leveringen (`tectora_roof_stock`), dus de
  stuklijst op maat voedt die materiaallijst;
* geen verborgen dienstlijnen met eigen taken/projecten per dienstcomponent:
  werkuren lopen in Tectora via de tijdnormen en de taken Afbraak- en
  Uitvoeringswerken;
* niet beperkt tot kit-stuklijsten: elke productlijn kan een stuklijst op maat
  krijgen, ook een product zonder stuklijst;
* de prijs van de orderlijn verandert alleen op vraag (*Opslaan en prijs
  toepassen*), omdat de prijzen uit het prijsboek komen;
* "Override BOM", dat de gekoppelde stuklijst overschreef, is *Opslaan als
  standaardstuklijst* geworden, zonder de meegeleverde sets te raken.
