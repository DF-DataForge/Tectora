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
| **Levering aan magazijn** (standaard) | Ontvangst-operatie van het magazijn. Eén order per leverancier, lijnen per dakproject gegroepeerd onder een sectielijn. Bevestigen maakt een ontvangst in het magazijn. |
| **Uit voorraad — niet bestellen** | Het materiaal ligt in het magazijn; er wordt niets besteld. De ploeg neemt het mee (of haalt het af bij een dropship). |

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

## Inkoop organiseren (het bestelbord)

*Dakmeting → Inkoop organiseren*, of de knop **Inkoop organiseren** op een
dakproject (dan enkel dat project). Een kanban met één kolom per logistieke
route: *Dropship*, *Levering aan magazijn*, *Uit voorraad*. De kaarten staan
per leverancier gesorteerd en tonen:

* de leverancier (rood als er geen is), het product en de hoeveelheid;
* de **vrije voorraad** in het magazijn en het tekort, als gekleurde badge
  (groen: volledig op voorraad, oranje: deels, rood: niet); de linkerrand van
  de kaart kleurt mee;
* de inkoopstatus, het dakproject en de geplande start van de werf;
* de inkooporder zodra die er is.

**Sleep een kaart naar een andere kolom** om te beslissen hoe dat materiaal
aangeleverd wordt; de route van de lijn volgt. De voortgangsbalk per kolom
toont hoeveel er nog te bestellen is. **Inkooporders aanmaken** bovenaan
bestelt alles op het bord, of enkel de geselecteerde kaarten.

De lijst *Materiaalbehoefte* opent per dakproject en per leverancier en
toont dezelfde kolommen (vrije voorraad, voorraadstatus, route, status), met
filters op status, route en voorraad.

## Inkooporders aanmaken

Vanuit *Dakmeting → Materiaalbehoefte* (of de *Materiaallijst* van een
dakproject, of het menu *Actie* van de lijst): lijnen selecteren en
**Inkooporders aanmaken**. De wizard toont welke orders er komen, met het
geschatte bedrag en de verwachte leverdatum, en laat toe:

* één route of één leverancier op te leggen voor de hele selectie;
* magazijnorders toch per dakproject te splitsen (standaard: één per
  leverancier, lijnen per dakproject gegroepeerd);
* een gewenste leverdatum te geven;
* de afhaling aan het magazijn op de dropship-orders te vermelden, met een
  extra toelichting;
* de orders meteen te bevestigen (standaard blijven het offerteaanvragen).

### Dropship-order

Altijd één dakproject. De order draagt het werfadres als leveradres, de
projectreferentie (code — naam, werfadres) als herkomst, en de **geplande
start van de werf** als verwachte leverdatum van elke lijn; die datum staat
in een banner op de order en op de afdruk voor de leverancier.

Heeft hetzelfde dakproject ook materiaal dat aan het magazijn geleverd wordt
of uit voorraad komt, dan krijgt de dropship-order de vlag **Extra materiaal
af te halen aan het magazijn** met de lijst van dat materiaal (product,
hoeveelheid, route, leverancier, status). Die lijst staat als waarschuwing op
de inkooporder, op de tab Materiaallijst van het dakproject, en wordt in de
chatter van het dakproject en van het planbare project gepost.

### Magazijnorder

Eén order per leverancier. De lijnen staan per dakproject gegroepeerd onder
een sectielijn *code — naam, werfadres — start werf datum*, in volgorde van
geplande start; de standaardafdruk toont die secties aan de leverancier. Elke
lijn draagt het dakproject en de analytische rekening van zijn project.

De orderlijnen worden geprijsd via Odoo's eigen leveranciersprijslijst-logica
(`purchase.order.line._prepare_purchase_order_line`, dezelfde weg als de
bevoorradingsmotor), dragen de analytische rekening van het project — zodat
de inkoop op het projectdashboard verschijnt — en hetzelfde materiaal uit
twee verkochte werkposten komt één keer op de order. De inkooporder
vermeldt het dakproject en de route en heeft een knop naar de materiaallijnen.

Een materiaallijn onthoudt haar inkooplijn en toont de **inkoopstatus**:
*Te bestellen*, *Uit voorraad*, *Offerteaanvraag*, *Besteld*, *Ontvangen*
(met de ontvangen hoeveelheid). Een geannuleerde inkooporder zet de lijnen terug op *Te
bestellen*. Filters en groeperingen op leverancier, route, status en
inkooporder staan in het overzicht. Diensten (arbeid uit een stuklijst) en
al bestelde lijnen worden nooit meebesteld.

## Rechten

Inkooporders aanmaken vraagt de groep *Inkoop / Gebruiker*; de knoppen zijn
enkel voor die groep zichtbaar. Logistieke routes beheren vraagt *Inkoop /
Beheerder*.

## Bestelbon materialen (transport)

Een inkooporder van een dakproject heeft een tweede document voor de
leverancier, **Bestelbon materialen – leverancier** (Afdrukken → *Bestelbon
materialen (transport)*). Wanneer de order naar de leverancier gemaild wordt
(offerteaanvraag of inkooporder), gaat de bestelbon automatisch als tweede pdf
mee.

| Rubriek | Bron |
|---|---|
| 1. Projectgegevens | dakproject (code, klant, werfadres), referentie van de leverancier op de order, *Hoogte dak(en)* en *Bereikbaarheid dak (i.f.v. camionkraan)* uit de tab Werf, de geplande leverdatum van de order |
| 2. Leveringsinstructies | *Materiaal rechtstreeks op het dak*, *Materialen op grond plaatsen* en *Afval mee te nemen door leverancier* uit de tab Werf (JA/NEE) |
| 3. Fotomateriaal | de foto's *Bovenaanzicht*, *Gevelaanzicht* en *Transportvoorbeeld* uit de tab Werf (enkel die er zijn) |
| 4. Lijst materialen bestelling | de producten op de inkooporder |
| 5. Op te halen in loods | de projectmaterialen die uit het eigen magazijn komen: uit voorraad en geleverd aan het magazijn, met het adres van het magazijn |

