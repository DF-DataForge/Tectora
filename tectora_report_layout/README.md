# Data Forge — Documentlay-out Tectora

Voegt de lay-out **Tectora** toe aan *Instellingen → Documentlay-out
configureren*, naast Light, Boxed, Bold, Striped, Bubble, Wave en Folder.

De header is de Tectora-dakrand: een zachte luchttint met de lijn van een
plat dak over de volle paginabreedte, links het logo en de slogan, rechts de
bedrijfsgegevens. De titel, tabelkoppen, totalen en de voettekstlijn nemen de
**hoofdkleur** van het bedrijf over; de dakrand zelf ook. Zoals elke lay-out
volgt ze de kleuren, het lettertype, het logo, de slogan, de voettekst en de
papierachtergrond uit de configurator, en ze geldt voor **alle documenten**
die via de externe lay-out afgedrukt worden: offertes en orders, facturen,
leveringen, inkooporders en de Dakmeting-bladen (meetblad, werfblad).

Bij installatie schakelt elk bedrijf over op deze lay-out; een bedrijf zonder
hoofdkleur krijgt het Tectora-teal `#008B93`. Een andere lay-out kiezen blijft
mogelijk in de configurator.

## Briefpapier

Drie lay-outs volgen het Tectora-briefpapier (`tectora-briefpapier-A4`):

* **Tectora Briefpapier**: bovenaan een band over de volle breedte in de
  hoofdkleur met het witte Tectora-logo en slogan links, de diensten en de
  website rechts; onderaan een lichtgrijze band met drie gecentreerde regels
  en een kort lijntje in de hoofdkleur aan de rechterrand.
* **Tectora Briefpapier licht**: de tweede kleurvariant van het briefpapier,
  met een lichtgrijze band bovenaan (logo in zijn eigen kleuren, diensten in
  grijs, website in de hoofdkleur) en de voetband in de hoofdkleur met witte
  tekst en een wit lijntje.
* **Tectora Briefpapier met dakrand**: hetzelfde briefpapier, maar de
  onderkant van de band is de dakrand (laagst links, de nok op driekwart),
  met de lichte dakrandband en de noklijn eronder.

Wat er staat, komt uit de bedrijfsgegevens:

| Plaats | Bron |
|---|---|
| Diensten (rechts in de band) | *Slogan* van de documentlay-out; leeg → "EPDM - roofing - isolatie - onderhoud - herstellingen" |
| Website (eronder, vet) | website van het bedrijf, zonder `https://` |
| Voet, regel 1 | naam — straat, postcode gemeente — btw-nummer (`BE 1031.956.670`) |
| Voet, regel 2 | *Voettekst* van de documentlay-out (bv. "Kantoor en werkplaats — Molstraat 102, 8870 Izegem — info@tectora.be — 0472 09 20 98"); leeg → e-mail — telefoon |
| Voet, regel 3 | bankrekeningen van het bedrijf (bank + rekeningnummer per vier) |

De band en het lijntje nemen de hoofdkleur; het briefpapier gebruikt teal
`#2D8D8F`. Het logo is een vector uit het briefpapier, niet het
bedrijfslogo: wit op de gekleurde band (`static/src/img/tectora_logo_white.svg`),
donker met teal accenten op de lichte band (`static/src/img/tectora_logo.svg`;
die accenten blijven `#2D8D8F`). Maten en lettergroottes (Montserrat) zijn op het
A4-origineel gemeten.

## Technisch

* `report.layout`-record `report_layout_tectora` → sjabloon
  `external_layout_tectora`, opgebouwd uit de gedeelde bouwstenen van Odoo 20
  (`web.company_address_list`, `web.external_layout_body`,
  `web.external_layout_footer_content`) met een eigen header-vorm.
* Het tabelontwerp (Licht, Gestreept, ...) is sinds Odoo 20 een eigen keuze in
  de documentlay-out; bij installatie (en bij de upgrade naar 20.0) krijgt een
  bedrijf dat nog op de standaard staat *Gestreept*, het ontwerp waarmee de
  lay-out getekend is.
* De dakrand staat als inline SVG in `tectora_header_shape`, getekend in de
  hoofdkleur; `static/src/img/header_bg.svg` is dezelfde tekening als los
  bestand. Wie liever de originele foto gebruikt, vervangt de `<svg>` in dat
  sjabloon door een `<img>` naar een PNG in `static/src/img/`.
* Kleurregels per bedrijf staan in een uitbreiding van
  `web.styles_company_report`; de vaste stijl in
  `static/src/scss/layout_tectora.scss` (bundel `web.report_assets_common`).
* De offerte-pdf van Dakmeting heeft eigen dossierstijlen; kies daar
  *Standaard Odoo-document* om ook die met deze lay-out te printen.
