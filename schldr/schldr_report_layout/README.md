# Data Forge — Documentlay-out Schldr

Voegt de lay-out **Schldr** toe aan *Instellingen → Documentlay-out
configureren*, naast Light, Boxed, Bold, Striped, Bubble, Wave en Folder.

De header is de accentrand: een zachte tint met een schuine lijn
over de volle paginabreedte, links het logo en de slogan, rechts de
bedrijfsgegevens. De titel, tabelkoppen, totalen en de voettekstlijn nemen de
**hoofdkleur** van het bedrijf over; de accentrand zelf ook. Zoals elke lay-out
volgt ze de kleuren, het lettertype, het logo, de slogan, de voettekst en de
papierachtergrond uit de configurator, en ze geldt voor **alle documenten**
die via de externe lay-out afgedrukt worden: offertes en orders, facturen,
leveringen, inkooporders en de Schldr-bladen (meetblad, werfblad).

Bij installatie schakelt elk bedrijf over op deze lay-out; een bedrijf zonder
hoofdkleur krijgt het Schldr-blauw `#2F5D8A`. Een andere lay-out kiezen blijft
mogelijk in de configurator.

## Briefpapier

Drie lay-outs volgen het Schldr-briefpapier (`schldr-briefpapier-A4`):

* **Schldr Briefpapier**: bovenaan een band over de volle breedte in de
  hoofdkleur met het witte Schldr-logo en slogan links, de diensten en de
  website rechts; onderaan een lichtgrijze band met drie gecentreerde regels
  en een kort lijntje in de hoofdkleur aan de rechterrand.
* **Schldr Briefpapier licht**: de tweede kleurvariant van het briefpapier,
  met een lichtgrijze band bovenaan (logo in zijn eigen kleuren, diensten in
  grijs, website in de hoofdkleur) en de voetband in de hoofdkleur met witte
  tekst en een wit lijntje.
* **Schldr Briefpapier met accentrand**: hetzelfde briefpapier, maar de
  onderkant van de band is de accentrand (laagst links, de nok op driekwart),
  met de lichte lichte band en de noklijn eronder.

**Schldr Briefpapier met accentrand** zet bovenaan het document ook de
partijen: links Schldr (naam, adres, telefoon) met de contactgegevens van de
verkoper (telefoon, e-mail; bij een inkooporder de aankoper) en de website,
rechts de klant en het **werfadres** (het adres van het schilderproject, anders het
leveradres).

Wat er staat, komt uit de bedrijfsgegevens:

| Plaats | Bron |
|---|---|
| Diensten (rechts in de band) | *Slogan* van de documentlay-out; leeg → "Schilderwerken - behang - decoratie - renovatie" |
| Website (eronder, vet) | website van het bedrijf, zonder `https://` |
| Voet, regel 1 | naam — straat, postcode gemeente — btw-nummer (`BE 1031.956.670`) |
| Voet, regel 2 | *Voettekst* van de documentlay-out (bv. "Kantoor en werkplaats — Molstraat 102, 8870 Izegem — info@schldr.be — 0472 09 20 98"); leeg → e-mail — telefoon |
| Voet, regel 3 | bankrekeningen van het bedrijf (bank + rekeningnummer per vier) |

De band en het lijntje nemen de hoofdkleur; het briefpapier gebruikt blauw
`#3A6A99`. Het logo is een vector uit het briefpapier, niet het
bedrijfslogo: wit op de gekleurde band (`static/src/img/schldr_logo_white.svg`),
donker met blauwe accenten op de lichte band (`static/src/img/schldr_logo.svg`;
die accenten blijven `#3A6A99`). Maten en lettergroottes (Montserrat) zijn op het
A4-origineel gemeten.

## Technisch

* `report.layout`-record `report_layout_schldr` → sjabloon
  `external_layout_schldr`, opgebouwd uit de gedeelde bouwstenen van Odoo 20
  (`web.company_address_list`, `web.external_layout_body`,
  `web.external_layout_footer_content`) met een eigen header-vorm.
* Het tabelontwerp (Licht, Gestreept, ...) is sinds Odoo 20 een eigen keuze in
  de documentlay-out. Daar staat ook **Schldr**: koppen in de hoofdkleur met
  een dikke lijn eronder, het totaal in een lichte tint, de informatieband
  tussen twee lijnen en wat meer ruimte tussen de offertelijnen. Het is te
  kiezen bij elke lay-out, en bij een Schldr-lay-out werken de andere
  ontwerpen ook. Bij installatie krijgt een bedrijf op de standaard *Schldr*.
* De accentrand staat als inline SVG in `schldr_header_shape`, getekend in de
  hoofdkleur; `static/src/img/header_bg.svg` is dezelfde tekening als los
  bestand. Wie liever de originele foto gebruikt, vervangt de `<svg>` in dat
  sjabloon door een `<img>` naar een PNG in `static/src/img/`.
* Kleurregels per bedrijf staan in een uitbreiding van
  `web.styles_company_report`; de vaste stijl in
  `static/src/scss/layout_schldr.scss` (bundel `web.report_assets_common`).
* De offerte-pdf van Schldr heeft eigen dossierstijlen; kies daar
  *Standaard Odoo-document* om ook die met deze lay-out te printen.
