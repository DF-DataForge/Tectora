# 12 — Van verkooporder tot bestelling

* **Duur**: ± 7:00
* **Doelpubliek**: nieuwe gebruikers: verkoop, calculatie, projectleiding, aankoop
* **Doel**: stap voor stap tonen hoe een product op een verkooporder via de
  stuklijst een correcte logistieke opvolging krijgt: producten op de order,
  de stuklijst (met de omrekening via lengte × breedte × hoogte per m en m²
  en een vast product), het project, de bestellijst (uit het magazijn, bij
  leverancier 1 en bij leverancier 2) en de materiaallijst die alles bijhoudt.
* **Voorbeeld (fictief)**: Bouwbedrijf Vandenbroucke bouwt in Waregem een
  garage van 10 × 6 m en bestelt het platte dak: 60 m² dak en 32 m dakrand.
  Eenvoudig gehouden: geen offertesjablonen en geen secties.

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:05 | Openingskaart. | — | **Van verkooporder tot bestelling** |
| 2 | 0:05–0:30 | Kaart met het overzicht: Verkooporder → Stuklijst → Project → Bestellijst → Magazijn · Leverancier 1 · Leverancier 2 → Materiaallijst. | In deze video volgen we één order van begin tot einde: van de producten op een verkooporder tot de bestellingen bij de leveranciers. Ons voorbeeld: Bouwbedrijf Vandenbroucke bouwt een garage van tien op zes meter en bestelt bij ons het platte dak. Dat is zestig vierkante meter dak en tweeëndertig meter dakrand. | Eén order, van verkoop tot bestelling |
| 3 | 0:30–0:52 | Inkoop → **Producten** → zoeken "Plat dak" → fiche **Plat dak: isolatie en EPDM**: **Productsoort** **Dienst**, **Verkoopprijs** 68,00 € per m². | We verkopen twee werkposten. Plat dak, isolatie en EPDM, per vierkante meter. En dakrand aluminium, per lopende meter. Het zijn diensten: de klant koopt een afgewerkt dak, niet de losse materialen. Welke materialen er nodig zijn, leggen we zo meteen vast in de stuklijst. | Verkopen: werkposten |
| 4 | 0:52–1:22 | Fiche **PIR-plaat 120 mm**: **Productsoort** **Goederen**, **Voorraad bijhouden** aan, **Kostprijs** 11,40 € per **Stuk(s)**; **Hercalculatie** aangevinkt, **Reken-UoM** **m²**, **Afmetingen (L × B × H)** 1.200 × 600 × 120 mm "= 0,7200 m² per stuk", **Veiligheidsmarge** 5 %. | De materialen zijn goederen die we per stuk kopen, zoals deze PIR-plaat. Bij Hercalculatie geeft u de afmetingen van één plaat in millimeter: lengte, breedte en hoogte. Omdat we in vierkante meter rekenen, telt Tectora lengte maal breedte: nul komma zeventwee vierkante meter per plaat. De hoogte, hier de dikte, telt dan niet mee. De veiligheidsmarge van vijf procent dekt het snijverlies. | L × B = m² per stuk |
| 5 | 1:22–1:40 | Fiche **EPDM-rol 15 × 3,05 m**: Reken-UoM m², 15.000 × 3.050 mm "= 45,75 m² per stuk", veiligheidsmarge 10 %. | Hetzelfde voor de EPDM. Eén rol is vijftien op drie komma nul vijf meter: vijfenveertig komma vijfenzeventig vierkante meter. Hier rekenen we tien procent marge, voor de overlappingen. | Ook voor rollen |
| 6 | 1:40–2:02 | Fiche **Dakrandprofiel 3 m**: **Reken-UoM** **m**, lengte 3.000 mm "= 3,0000 m per stuk", veiligheidsmarge 5 %; veld **Aanwezige voorraad** 20,00 Stuk(s). | Bij de rekeneenheid meter telt enkel de lengte. Een dakrandprofiel is drie meter lang. Zo rekent Tectora lopende meters om naar profielen. Van deze profielen liggen er twintig in ons eigen magazijn, net als twaalf potten contactlijm. | m: enkel de lengte |
| 7 | 2:02–2:22 | Verkoop → **Offertes** → **Nieuw** → **Nieuwe offerte**; **Klant** Bouwbedrijf Vandenbroucke. | Nu de verkooporder. In Verkoop maakt u een nieuwe offerte, zonder sjabloon. Kies de klant: Bouwbedrijf Vandenbroucke. | Nieuwe offerte |
| 8 | 2:22–2:50 | **Regel toevoegen** → "Plat dak: isolatie en EPDM", **Aantal** 60 m²; **Regel toevoegen** → "Dakrand aluminium", aantal 32 m; **Opslaan**. | Met Regel toevoegen zet u de werkposten op de offerte: zestig vierkante meter plat dak en tweeëndertig meter dakrand. De prijs komt van het product. Sla de offerte op: pas dan kan u de stuklijsten openen. | Producten op de order |
| 9 | 2:50–3:10 | Icoon naast de daklijn (tooltip **Stuklijst aanpassen**) → venster **Stuklijst: Plat dak: isolatie en EPDM**, nog zonder componenten. | Achter elke werkpost zit een stuklijst: de materialen die nodig zijn. Deze werkpost heeft er nog geen. U opent ze met het kleine icoon naast de lijn. | De stuklijst openen |
| 10 | 3:10–3:42 | **Regel toevoegen** → PIR-plaat, **Hoeveelheid** 1,00 per m²; kolommen **Totaal** 60,00 m², **Extra marge %** 5, **Stuks** 88; tooltip op 88: "60,00 m² + 5 % = 63,00 m² ÷ 0,72 m² per stuk = 87,50 stuks → 88 stuks op de materiaallijst". | Met Regel toevoegen kiest u een materiaal en de hoeveelheid per verkochte eenheid: één vierkante meter PIR per vierkante meter dak. Totaal: zestig vierkante meter. Plus vijf procent marge is drieënzestig, gedeeld door nul komma zeventwee per plaat: zevenentachtig en een half. Tectora rondt altijd naar boven af: achtentachtig platen. | 60 m² → 88 platen |
| 11 | 3:42–4:00 | EPDM-rol, hoeveelheid 1,00 → **Stuks** 2 (tooltip "60,00 m² + 10 % = 66,00 m² ÷ 45,75 m² per stuk = 1,44 stuks → 2 stuks"). Contactlijm, hoeveelheid 0,05 → **Stuks** 3. | Voor de EPDM: zesenzestig vierkante meter, dat is twee rollen. De contactlijm heeft geen afmetingen: één pot per twintig vierkante meter, dus nul komma nul vijf per vierkante meter. Samen drie potten. | Rollen en potten |
| 12 | 4:00–4:24 | Container 6 m³, hoeveelheid 1, **Vast** aangevinkt → **Totaal** 1, **Stuks** 1; bovenaan **Kostprijs per eenheid** 34,12. | De container is een vast product. Vink Vast aan: hij telt één keer voor de hele lijn, hoe groot het dak ook is. Zijn kost wordt wel verdeeld over de vierkante meters. Daarom bevat de kostprijs per eenheid hierboven ook een deel van de container: samen vierendertig euro twaalf per vierkante meter. | Vast = één keer per lijn |
| 13 | 4:24–4:46 | **Marge (%)** 100 → **Berekende prijs** 68,24 (naast **Huidige prijs** 68,00) → **Opslaan en prijs toepassen** → **Ok**; prijs op de lijn 68,24. | Met de marge berekent Tectora de verkoopprijs: honderd procent marge geeft achtenzestig euro vierentwintig. Met Opslaan en prijs toepassen komt die prijs op de lijn. | Kost + marge = prijs |
| 14 | 4:46–5:02 | Icoon opnieuw (nu **Stuklijst op maat**) → **Opslaan als standaardstuklijst** → **Ok**. | Wilt u deze samenstelling elke keer gebruiken? Open de stuklijst opnieuw en kies Opslaan als standaardstuklijst. Elke volgende offerte met dit product vertrekt er dan van. | Standaard voor volgende offertes |
| 15 | 5:02–5:20 | Stuklijst van de dakrandlijn: Dakrandprofiel 3 m, hoeveelheid 1 per m → **Stuks** 12 (tooltip "32,00 m + 5 % = 33,60 m ÷ 3 m per stuk = 11,20 stuks → 12 stuks") → **Opslaan**. | Ook de dakrand krijgt een stuklijst: één meter profiel per meter dakrand. Tweeëndertig meter plus vijf procent, gedeeld door drie meter per profiel: twaalf profielen. | 32 m → 12 profielen |
| 16 | 5:20–5:36 | **Bevestigen** → status **Verkooporder**; slimme knop **Projectdashboard**. | De klant gaat akkoord. Bevestig de order: Tectora maakt meteen het project aan, met de materiaallijst. | Bevestigen = project |
| 17 | 5:36–6:02 | **Projectdashboard** → tab **Materiaallijst**: PIR-plaat 88, EPDM-rol 2, Contactlijm 3, Container 1, Dakrandprofiel 12, telkens Stuk(s), met **Leverancier**; kolom **Bestellijst**: **Niet op de bestellijst**. Via het kolomicoon de kolommen **Inkooporder** en **Inkoopstatus** verbergen. | Op het projectdashboard staat de materiaallijst: alle stuklijsten samen, in stuks. Achtentachtig platen, twee rollen, drie potten lijm, één container en twaalf profielen, met hun leverancier. In de kolom Bestellijst ziet u dat er nog niets geregeld is. Kolommen die u niet nodig heeft, verbergt u met het icoontje rechts. | De materiaallijst |
| 18 | 6:02–6:24 | Blok **Bestellijst** → **Openen** → pagina **Bestellijst**: onderdeel **Materialen**, **Leverancier** Bouwmaterialen De Smet → knop **Producten**: Container, PIR-plaat, Contactlijm (· in stock: 12), Dakrandprofiel (· in stock: 20). | Nu bestellen we. Open de bestellijst. Kies de leverancier en klik op Producten: u ziet de materialen van dit project die u bij die leverancier koopt, met wat er nodig is en wat er op voorraad ligt. | De bestellijst |
| 19 | 6:24–6:42 | Contactlijm en Dakrandprofiel aanvinken → **Leveren vanuit stock** → groep **Leveren vanuit magazijn** WH/OUT/… met beide producten **Gereserveerd**. | De lijm en de profielen hebben we zelf. Vink ze aan en kies Leveren vanuit stock. Tectora maakt een levering van het magazijn naar de werf en reserveert de voorraad. | Uit het eigen magazijn |
| 20 | 6:42–7:06 | PIR-plaat en Container aanvinken → **Bestellen** → offerteaanvraag P… bij Bouwmaterialen De Smet met 88 platen en 1 container, veld **Bestellijst-onderdeel** Materialen → **Bevestig order** → terug naar de bestellijst. | De platen en de container bestellen we bij leverancier één, Bouwmaterialen De Smet. Vink ze aan en klik op Bestellen. De bestelling staat klaar, met het project als referentie. Bevestig ze. | Leverancier 1 |
| 21 | 7:06–7:28 | **Leverancier** → Dakcenter Vlaanderen → **Producten**: EPDM-rol, nodig 2 → aanvinken → **Bestellen** → **Bevestig order** → terug; "Alles van dit onderdeel is besteld of komt uit het magazijn." met de groepen per leverancier en het magazijn. | De EPDM bestellen we bij leverancier twee. Kies Dakcenter Vlaanderen, vink de rollen aan en bestel. Nu is alles geregeld: per leverancier ziet u de bestelling, en apart wat uit het magazijn komt. | Leverancier 2 |
| 22 | 7:28–7:52 | Terug naar het **Projectdashboard** → **Materiaallijst**: kolom **Bestellijst** "Besteld" (PIR, container: P… Bouwmaterialen De Smet; EPDM: P… Dakcenter Vlaanderen) en "Magazijn: gereserveerd" (lijm, profielen: WH/OUT/…); kaart **Inkoop**: 2 inkooporders. | En op de materiaallijst ziet u het allemaal terug. Per product: besteld, bij welke leverancier en op welke bestelling, of gereserveerd in het magazijn met de levering erbij. Zodra de goederen binnenkomen of vertrekken, volgt de status vanzelf. | Alles op de materiaallijst |
| 23 | 7:52–8:10 | Kaart met de samenvatting: 1. Werkposten op de order · 2. Stuklijst: L × B × H rekent om naar stuks, vast product één keer · 3. Bevestigen = project · 4. Bestellijst: magazijn of leverancier · 5. Materiaallijst volgt alles. | Samengevat: werkposten op de order, de stuklijst rekent om naar stuks, bevestigen maakt het project, en via de bestellijst bestelt u bij de juiste leverancier of levert u uit het magazijn. De materiaallijst houdt alles bij. | Samengevat |
| 24 | 8:10–8:15 | Eindkaart. | — | Van verkooporder tot bestelling |

## Rekenvoorbeelden (nagekeken in Tectora)

| Materiaal | Per verkochte eenheid | Totaal | Omrekening | Op de materiaallijst |
|---|---|---|---|---|
| PIR-plaat 1200 × 600 × 120 mm (m²) | 1,00 m² per m² | 60 m² | 60 + 5 % = 63 m² ÷ 0,72 = 87,50 | **88 platen** |
| EPDM-rol 15 × 3,05 m (m²) | 1,00 m² per m² | 60 m² | 60 + 10 % = 66 m² ÷ 45,75 = 1,44 | **2 rollen** |
| Contactlijm 5 l | 0,05 pot per m² | 3 potten | geen omrekening | **3 potten** |
| Container 6 m³ | 1, **Vast** | 1 | geen omrekening | **1 container** |
| Dakrandprofiel 3 m (m) | 1,00 m per m | 32 m | 32 + 5 % = 33,6 m ÷ 3 = 11,2 | **12 profielen** |

Kostprijs per m² van de daklijn: (88 × 11,40 + 2 × 310 + 3 × 48 + 280) ÷ 60 =
2.047,20 ÷ 60 = **34,12 €**; met 100 % marge **68,24 €**.

## Opnametips

* Demodata: `VIDEO_STAGE=so_logistics` in `tools/video_pipeline/seed_demo.py`
  (fictieve producten, stock voor lijm en profielen, leveranciers en één
  bestellijst-onderdeel "Materialen"). De werkposten hebben bij de start geen
  stuklijst: de video bouwt ze.
* **Opslaan als standaardstuklijst** vraagt de rol beheerder Productie.
* De materiaallijst toont naast de kolom **Bestellijst** ook **Inkooporder** en
  **Inkoopstatus**: die horen bij het bestellen vanuit de materiaallijst zelf
  ("Inkoop organiseren") en blijven leeg als u via de bestellijst bestelt.
  Daarom verbergt de video ze.
