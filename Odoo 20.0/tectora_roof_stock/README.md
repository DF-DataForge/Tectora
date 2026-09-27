# Data Forge Dakmeting — Voorraad

Brug tussen de dakprojecten en de app Voorraad: de **materiaallijst** van een
dakproject wordt een **uitgaande levering**. Installeert zichzelf zodra
Dakmeting en Voorraad (met de verkoopkoppeling `sale_stock`) aanwezig zijn.

## Levering klaarzetten

Op het dakproject (knop **Levering klaarzetten** in de kop en onder de tab
*Materiaallijst*) en op het projectdashboard (tab *Materiaallijst*):

* één levering van het type *Leveringen* van het magazijn van het bedrijf,
  met **één regel per materiaal**: de materiaallijst wordt per product
  opgeteld (dezelfde primer uit drie stuklijsten is één regel), in de eenheid
  van het product;
* **diensten** op de lijst (werkuren) bewegen niet en worden overgeslagen;
* bestemd voor de **werf**: het leveradres van de order, anders de klant;
  bron: de standaardlocatie van de leveringsbewerking; herkomst
  "*ordernummer / dakproject*";
* **gepland** op de geplande start van het dakproject, anders nu;
* **bevestigd** bij aanmaak, zodat het magazijn ze ziet en reserveert wat er
  is; het bureau valideert wanneer de camion geladen is.

Elke levering draagt het dakproject (veld *Dakproject*, ook zoekbaar in de
leveringslijst). De teller **Leveringen** op het dakproject en de kaart
Leveringen op het dashboard tellen de materiaalleveringen mee; de knop
**Materiaalleveringen** toont ze apart.

## Nog eens klaarzetten

Opnieuw klikken levert alleen wat **nog niet op een levering staat**: de
hoeveelheden op de bestaande materiaalleveringen van het project (wachtend,
klaar of gedaan) worden afgetrokken. Groeit de materiaallijst na een
meerwerk, dan geeft een tweede klik één levering met het verschil; staat alles
al op een levering, dan zegt de knop dat. Een geannuleerde levering telt niet
mee en wordt dus opnieuw klaargezet.

## Technisch

* `tectora.roof.project`: `material_picking_ids`, `material_picking_count`,
  `action_create_material_picking()`, `action_view_material_pickings()`;
  `_get_pickings()` neemt de materiaalleveringen mee.
* `stock.picking.tectora_roof_project_id`.
* De levering hangt via het dakproject aan de order, niet via `sale_id`: Odoo
  19 herrekent dat veld uit de verkooporderlijnen van de bewegingen, en deze
  bewegingen horen bij geen orderlijn (de verkochte posten zijn diensten).
* Tests in `tests/test_material_picking.py`.
