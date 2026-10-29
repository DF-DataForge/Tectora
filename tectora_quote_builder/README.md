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
| Eigen kop enkel op pagina's | leeg = alle | bv. `1,2,4`: enkel die pagina's hebben bovenaan een band of logo |
| Eigen voet enkel op pagina's | leeg = alle | bv. `1,4`: enkel die pagina's hebben een voetband |
| Verkleinen op pagina's | leeg = geen | bv. `3`: die pagina's lopen tot tegen de rand en worden verkleind tot ze tussen de kop en voet van de lay-out passen |

De pagina blijft **op ware grootte** (geen witte randen); de kop en voet van de
lay-out komen erover. Heeft de kop van de lay-out een schuine onderkant (de
dakrand van *Tectora Briefpapier met dakrand*), dan wordt de eigen band van de
pdf langs die dakrand weggeknipt, niet recht: zo blijft er geen witte wig
onder de nok en geen stuk van de eigen dakrand van de pdf. *Eigen kop
weglaten* is dan het minimum: dieper dan de dakrand knipt het enkel waar die
hoogte lager ligt. Onder de eigen band van de pdf (die wegvalt) staat dus de
kop of voet van de lay-out. Is de voet van de lay-out lager dan de eigen voet
van de pdf, dan blijft daar wit; zet *Eigen voet weglaten* op 0 om de voetband
van de pdf zelf te houden.

## Naam klant op de voorpagina

*Naam klant op de eerste pagina* (enkel bij een kop): de naam van de klant,
met de **aanspreektitel** van het contact ervoor ("Dhr. Michiels Philippe";
contact › *Aanspreektitel*, lijst in Verkoop › Configuratie ›
Aanspreektitels), en eronder het **werfadres** (het afleveradres van de
offerte, bv. "Werfadres: Lostraat 15, 1703 Schepdaal"), komt gecentreerd op de
eerste pagina, in de hoofdkleur van het bedrijf, op
*Positie naam klant* mm van de bovenkant van de oorspronkelijke pagina
(standaard 232 mm: onder "Voorstel op maat"). Enkel voor de eerste kop van de
offerte.

## Voorbeeld (pdf "Offerte 2026/0491")

- **Kop** = pagina 1–4 (voorpagina, introductie, kernwaarden en werkwijze,
  aanbrengactie): *Standaard toevoegen*, *Naam klant op de eerste pagina*,
  eigen kop 28 mm, eigen voet 24 mm *enkel op pagina's* `1,4`.
- **Voettekst** = pagina 13–17 (verkoopsvoorwaarden, werfregels,
  slotbepalingen, beeld- en geluidsmateriaal, dankwoord): *Standaard
  toevoegen*, eigen kop 28 mm *enkel op pagina's* `1,2,4,5`, eigen voet **0**
  (die pagina's hebben geen voetband), *verkleinen op pagina's* `3` (de
  slotbepalingen beginnen bovenaan de pagina).

## Technisch

- Het rapport *Lay-outkader offerte* (`report_layout_frame`) drukt per order
  de kop en voet van de lay-out op een verder lege, doorzichtige pagina (zonder
  adres of titel). Die wordt over elke pagina van de kop- en voetteksten gelegd
  (`ir.actions.report._tectora_put_in_frame`).
- wkhtmltopdf drukt geen kop en voet op een pagina met een lege body; het
  kader heeft daarom een onzichtbare lijn van 1 px.
- Kan het kader niet gemaakt worden, dan wordt het document afgedrukt zoals
  het is (en staat de fout in het log).
- Formuliervelden in een kop- of voettekst worden niet ondersteund wanneer die
  in de lay-out afgedrukt wordt.
