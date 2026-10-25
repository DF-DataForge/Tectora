# Videoscripts — de standaardflow van Tectora

Een reeks korte instructievideo's (1 à 2 minuten) voor het e-learningplatform.
Ze volgen één voorbeeldklant van de eerste aanvraag tot de uren op de werf,
zonder de tekenmodule Dakmeting (die krijgt een eigen reeks in
[`../dakmeting/`](../dakmeting/)).

**Bedrijf**: Tectora — **voorbeeldklant**: Familie Peeters.

| # | Video | Duur | Voor wie |
|---|---|---|---|
| 01 | [CRM: van aanvraag tot opportuniteit](01_crm.md) | 1:30 | verkoop |
| 02 | [De behoeften van de klant vastleggen](02_behoeften_vastleggen.md) | 1:30 | verkoop |
| 03 | [Een plaatsbezoek inplannen](03_afspraak_inplannen.md) | 1:15 | verkoop |
| 04 | [Een offerte maken en versturen](04_offerte_maken.md) | 1:45 | verkoop |
| 05 | [De opbouw van een Tectora-offerte](05_opbouw_offerte.md) | 1:45 | verkoop, calculatie |
| 06 | [De BOM builder: stuklijst op maat](06_bom_builder.md) | 1:45 | calculatie, verkoop |
| 07 | [Hercalculatie: van m² naar stuks](07_hercalculatie.md) | 1:45 | calculatie, aankoop |
| 08 | [Van offerte naar project](08_project_aanmaken.md) | 1:30 | projectleiding, zaakvoerder |
| 09 | [Taakopvolging per fase](09_taakopvolging.md) | 1:45 | projectleiding |
| 10 | [De bestellijst](10_bestellijsten.md) | 1:45 | projectleiding, aankoop |
| 11 | [Het werknemersportaal](11_werknemersportaal.md) | 1:45 | dakwerkers, ploegbazen |

## Conventies

* **Taal**: Nederlands (Vlaams), u-vorm in de voice-over, korte zinnen.
  Knoppen, velden en menu's staan **vet**, zoals ze in Odoo 20 (Nederlands)
  verschijnen. De labels zijn nagekeken in de code van de Tectora-modules en
  in de Nederlandse vertaling van Odoo; loop ze vóór de opname toch na in de
  eigen database.
* **Tempo**: ± 130 woorden per minuut. Tijdcodes zijn richtwaarden; de
  voice-over bepaalt de duur.
* **Kolommen**: *Beeld* = wat er op het scherm gebeurt; *Voice-over* = de
  gesproken tekst; *Tekst in beeld* = titel of ondertitel als overlay.
* **Opname**: schermopname 1920 × 1080, browser op 100 %, Odoo-menubalk
  zichtbaar. Klikken accentueren, inzoomen op het veld of de knop die
  genoemd wordt. Portaalbeelden (video 11) in mobiele weergave.
* **Huisstijl**: Tectora-teal `#2D8D8F`, lettertype Montserrat; openings- en
  eindkaart met het Tectora-logo, eindkaart verwijst naar de volgende video.
* **Automatisch opnemen**: met `tools/video_pipeline` (storyboard per video).

## Demodata (dezelfde in alle video's)

Zet dit klaar in een demodatabase (nooit in productie):

* **Bedrijf**: Tectora, documentlay-out **Tectora Briefpapier**.
* **Klant**: Familie Peeters, Kerkstraat 14, 8870 Izegem, aanspreektitel
  **Familie**, e-mailadres met een inbox die u kan tonen (video 03 en 04).
* **Opportuniteit**: "Renovatie plat dak Peeters", ± 100 m², verwachte
  omzet € 14.500, bron **Lead website**.
* **Offertesjabloon**: "Renovatie plat dak - roofing 1 laag, PIR 12 cm,
  EPDM 1,1 mm, 2-delige dakrand" (geladen via **Offertesjablonen laden**).
* **Hercalculatie** (video 07): een PIR-plaat 1200 × 600 mm (Reken-UoM m²,
  veiligheidsmarge 3 %) en een dakrandprofiel van 3000 mm (Reken-UoM m,
  veiligheidsmarge 5 %), beide als component in de stuklijst van de
  overeenkomstige werkpost.
* **Projectfases en taaksjablonen** (video 09): de module levert ze niet
  mee. Bijvoorbeeld 1. Voorbereiding (Plaatsbezoek bevestigen, Bestellijst
  afgevinkt, Stelling bestellen *optie*), 2. Uitvoering (Afbraak, Opbouw),
  3. Oplevering (Werf opleveren met klant, Eindfactuur).
* **Bestellijst-onderdelen** (video 10): ook niet meegeleverd. Bijvoorbeeld
  Lichtkoepels (Bestellen), Isolatie PIR (Bestellen), EPDM (Stock eerst),
  Dakrandprofielen (Bestellen), Container (Bestellen), met fictieve
  leveranciers "Dakcenter Vlaanderen" en "Bouwmaterialen De Smet".
* **Medewerkers**: projectleider, ploegbaas en twee dakwerkers; één
  dakwerker met werk-e-mail en portaaltoegang (video 11).
* **Apps**: CRM, Agenda, Verkoop (met Quote Builder), Productie (stuklijsten),
  Project, Urenstaten, Inkoop, Voorraad, plus de Tectora-modules.
