# Data Forge Dakmeting — Inkoop (`tectora_purchase`)

Bestelt de materiaalbehoefte van de dakprojecten bij de ingestelde
leveranciers. Installeert zichzelf zodra Dakmeting, Inkoop (`purchase_stock`)
en Dropshipping (`stock_dropshipping`) geïnstalleerd zijn.

## Logistieke routes

*Dakmeting → Logistieke routes* (ook onder *Inkoop → Configuratie*). Twee
routes staan klaar:

| Route | Wat gebeurt er op de inkooporder |
|---|---|
| **Dropship — levering op de werf** | Dropship-operatie van het bedrijf en het leveradres van het dakproject (leveradres van de order, anders de klant). Bevestigen maakt een dropship-levering leverancier → klant. |
| **Levering aan magazijn** (standaard) | Ontvangst-operatie van het magazijn. Bevestigen maakt een ontvangst in het magazijn. |

Een route is: een leveringstype, een magazijn (voor magazijnleveringen), de
operatie die de inkooporder krijgt en de overeenkomstige Odoo-voorraadroute.
Routes zijn aan te passen en uit te breiden (tweede magazijn, route per
bedrijf).

Welke route een materiaal volgt:

1. de **Logistieke route** op het product (productformulier, tab *Inkoop*,
   groep *Dakmeting*);
2. anders de Odoo-routes van het product of zijn categorie: draagt het
   product de route *Dropship*, dan dropship;
3. anders de route met *Standaardroute* aan (bij installatie: levering aan
   magazijn).

De route staat op elke materiaallijn en is daar per lijn te wijzigen.

## Leveranciers

Elke materiaallijn krijgt de leverancier uit de inkoopprijslijst van het
product (`product.supplierinfo`, de leveranciers die de productcatalogus
aanmaakt): de goedkoopste lijn voor de benodigde hoeveelheid, anders de
eerste leverancier. Per lijn te wijzigen; een handmatig gekozen leverancier
die het product levert blijft staan.

## Inkooporders aanmaken

Vanuit *Dakmeting → Materiaalbehoefte* (of de *Materiaallijst* van een
dakproject, of het menu *Actie* van de lijst): lijnen selecteren en
**Inkooporders aanmaken**. De wizard toont welke orders er komen — één per
leverancier, per logistieke route en per dakproject — met het geschatte
bedrag, en laat toe:

* één route of één leverancier op te leggen voor de hele selectie;
* magazijnleveringen van meerdere dakprojecten op één order te zetten
  (dropship blijft altijd per werf, want het leveradres verschilt);
* een gewenste leverdatum te geven;
* de orders meteen te bevestigen (standaard blijven het offerteaanvragen).

De orderlijnen worden geprijsd via Odoo's eigen leveranciersprijslijst-logica
(`purchase.order.line._prepare_purchase_order_line`, dezelfde weg als de
bevoorradingsmotor), dragen de analytische rekening van het project — zodat
de inkoop op het projectdashboard verschijnt — en hetzelfde materiaal uit
twee verkochte werkposten komt één keer op de order. De inkooporder
vermeldt het dakproject en de route en heeft een knop naar de materiaallijnen.

Een materiaallijn onthoudt haar inkooplijn en toont de **inkoopstatus**:
*Te bestellen*, *Offerteaanvraag*, *Besteld*, *Ontvangen* (met de ontvangen
hoeveelheid). Een geannuleerde inkooporder zet de lijnen terug op *Te
bestellen*. Filters en groeperingen op leverancier, route, status en
inkooporder staan in het overzicht. Diensten (arbeid uit een stuklijst) en
al bestelde lijnen worden nooit meebesteld.

## Rechten

Inkooporders aanmaken vraagt de groep *Inkoop / Gebruiker*; de knoppen zijn
enkel voor die groep zichtbaar. Logistieke routes beheren vraagt *Inkoop /
Beheerder*.
