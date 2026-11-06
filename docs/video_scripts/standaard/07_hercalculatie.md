# 07 — Hercalculatie: van m² naar stuks

* **Duur**: ± 1:45
* **Doelpubliek**: calculatie, aankoop
* **Doel**: een product instellen voor hercalculatie, zodat Tectora
  vierkante of lopende meters op de offerte omrekent naar het aantal
  platen, rollen of profielen om te bestellen.

| # | Tijd | Beeld | Voice-over | Tekst in beeld |
|---|---|---|---|---|
| 1 | 0:00–0:05 | Openingskaart. | — | **Hercalculatie: van m² naar stuks** |
| 2 | 0:05–0:17 | Offertelijn "100 m² isolatie" naast een stapel PIR-platen van 1200 × 600 mm. | U verkoopt isolatie per vierkante meter, maar u bestelt platen. Hoeveel platen heeft u nodig voor honderd vierkante meter? Dat rekent Tectora voor u uit. | Verkopen per m², bestellen per stuk |
| 3 | 0:17–0:42 | Productfiche PIR-plaat: **Hercalculatie** aanvinken → **Reken-UoM** **m²** → **Afmetingen (L × B × H)** 1200 × 600 mm → "= 0,7200 m² per stuk" → **Veiligheidsmarge** 3 % → **Kostprijs** … per **Stuk(s)** → opslaan. | Open het product en vink Hercalculatie aan. Kies de eenheid waarin u rekent, hier vierkante meter, en geef de afmetingen van één stuk in millimeter. Tectora toont meteen hoeveel één plaat is. Met de veiligheidsmarge rekent u snijverlies mee. De eenheid van het product zelf blijft Stuk: daarin koopt u, en daarin komen de aantallen op de materiaallijst. | Afmetingen in mm + marge |
| 4 | 0:42–0:57 | Tweede voorbeeld: dakrandprofiel (eenheid Stuk(s)), Reken-UoM **m**, lengte 3000 mm = 3 m per stuk, veiligheidsmarge 5 %. | Hetzelfde voor een dakrandprofiel: reken in lopende meter, met een lengte van drie meter per stuk. De veiligheidsmarge is hier vijf procent. | Ook per lopende meter |
| 5 | 0:57–1:18 | Productie → Stuklijsten → stuklijst van de werkpost isolatie (S00139): kolom **Omrekening** → "1,00 m² + 3 % = 1,03 m² ÷ 0,72 m² per stuk = 1,43 stuks". Daarna de BOM builder op de offerte Peeters (isolatielijn, 100 m²): "100,00 m² + 3 % = 103,00 m² ÷ 0,72 m² per stuk = 143,06 stuks → 144 stuks op de materiaallijst". | Open in Productie de stuklijst van de werkpost isolatie: in de kolom Omrekening ziet u de omrekening per eenheid. Open daarna op de offerte de BOM builder van de isolatielijn. Daar staat het resultaat voor deze werf: honderd vierkante meter, plus drie procent, wordt honderdvierenveertig platen. Tectora rondt altijd naar boven af. | 100 m² → 144 platen |
| 6 | 1:18–1:35 | **Bevestigen** → **Projectdashboard** → tab **Materiaallijst**: PIR-plaat 144,00 Stuk(s), dakrandprofiel 14,00 Stuk(s). | Bevestig de offerte en open het projectdashboard. Bij bevestiging komen die aantallen op de materiaallijst van het project. Zo bestelt de aankoop meteen het juiste aantal platen en profielen, in plaats van vierkante meters. | Juiste aantallen om te bestellen |
| 7 | 1:35–1:45 | Eindkaart. | Volgende video: van offerte naar project. | Volgende: van offerte naar project |

## Rekenvoorbeelden (nagekeken in de code)

* PIR 1200 × 600 mm = 0,72 m² per stuk. 100 m² + 3 % = 103 m² ÷ 0,72 =
  143,06 → **144 stuks**.
* Dakrandprofiel 3000 mm = 3 m per stuk. 38 m + 5 % = 39,9 m ÷ 3 = 13,3 →
  **14 stuks**.
* Afronden gebeurt naar boven, per orderlijn.

## Opnametips

* Pas de veiligheidsmarge niet toe op een stuklijst waarvan de normen al
  snijverlies bevatten (bv. EPDM 1,10 m² per m²): dan telt u het dubbel.
* Hercalculatie kan ook vanaf een variant (component) aangezet worden.
* De eenheid van het product (naast **Kostprijs**) moet **Stuk(s)** zijn, met de
  kostprijs per stuk: hercalculatie rekent om naar stuks van die eenheid. Staat
  de plaat in m² of het profiel in m, dan toont de materiaallijst "144,00 m²"
  en klopt de kost niet.
