# Kop- en voetteksten offerte (`tectora_quote_builder`)

De kop- en voetteksten van Odoo's *Quote Builder* (Verkoop › Configuratie ›
Kop- en voetteksten) als vaste structuur van elke offerte: voorpagina en
introductie vóór de offerte, voorwaarden en slotpagina erna.

## Automatisch op elke offerte

Elke nieuwe offerte krijgt de kop- en voetteksten met **Standaard toevoegen**.
Odoo doet dat zelf voor de documenten zonder offertesjabloon; die van het
offertesjabloon voegt Odoo enkel toe wanneer het sjabloon in het formulier
gekozen wordt. Deze module voegt ze ook toe aan offertes die in code ontstaan
(vanuit een dakproject, of met het standaardsjabloon van het bedrijf).

Zoals in Odoo komen de kop- en voetteksten op de **offerte**; op een bevestigd
order enkel met de instelling *Altijd de geselecteerde documenten toevoegen*.

## In de documentlay-out

Elke pagina van een kop- of voettekst krijgt de **kop en voet van de
documentlay-out** (Instellingen › Documentlay-out configureren), net als de
offerte zelf. Per document (tab *Afdrukken in de documentlay-out*):

| Veld | Standaard | |
|---|---|---|
| In de documentlay-out | aan | uit = de pdf wordt afgedrukt zoals hij is |
| Eigen kop weglaten (mm) | 28 | de band bovenaan de pdf zelf |
| Eigen voet weglaten (mm) | 24 | de voetband van de pdf zelf |
| Eigen voet enkel op pagina's | leeg = alle | bv. `1,4`: enkel die pagina's hebben een voetband |

Wat tussen de eigen kop en voet ligt, wordt verkleind tot het tussen de kop en
de voet van de lay-out past (gecentreerd, bovenaan uitgelijnd), zodat er niets
wegvalt.

## Naam klant op de voorpagina

*Naam klant op de eerste pagina* (enkel bij een kop): de naam van de klant
komt gecentreerd op de eerste pagina, in de hoofdkleur van het bedrijf, op
*Positie naam klant* mm van de bovenkant van de oorspronkelijke pagina
(standaard 232 mm: onder "Voorstel op maat"). Enkel voor de eerste kop van de
offerte.

## Voorbeeld (pdf "Offerte 2026/0491")

- **Kop** = pagina 1–4 (voorpagina, introductie, kernwaarden en werkwijze,
  aanbrengactie): *Standaard toevoegen*, *Naam klant op de eerste pagina*,
  eigen kop 28 mm, eigen voet 24 mm *enkel op pagina's* `1,4`.
- **Voettekst** = pagina 13–17 (verkoopsvoorwaarden, werfregels, beeld- en
  geluidsmateriaal, dankwoord): *Standaard toevoegen*, eigen kop 28 mm, eigen
  voet **0** (die pagina's hebben geen voetband; de inhoud loopt tot onderaan).

## Technisch

- Het rapport *Lay-outkader offerte* (`report_layout_frame`) drukt per order
  de kop en voet van de lay-out rond een lege pagina (zonder adres of titel).
  De pagina's van de kop- en voetteksten worden daarop geplaatst
  (`ir.actions.report._tectora_fit_into_frame`); de ruimte ertussen volgt de
  marges van het papierformaat van dat rapport.
- Kan het kader niet gemaakt worden, dan wordt het document afgedrukt zoals
  het is (en staat de fout in het log).
- Formuliervelden in een kop- of voettekst worden niet ondersteund wanneer die
  in de lay-out afgedrukt wordt.
