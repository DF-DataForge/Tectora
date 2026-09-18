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

## Technisch

* `report.layout`-record `report_layout_tectora` → sjabloon
  `external_layout_tectora` (opgebouwd zoals de Wave- en Folder-lay-outs van
  Odoo 19: header met een vaste vorm, artikel, voettekst).
* De dakrand staat als inline SVG in `tectora_header_shape`, getekend in de
  hoofdkleur; `static/src/img/header_bg.svg` is dezelfde tekening als los
  bestand. Wie liever de originele foto gebruikt, vervangt de `<svg>` in dat
  sjabloon door een `<img>` naar een PNG in `static/src/img/`.
* Kleurregels per bedrijf staan in een uitbreiding van
  `web.styles_company_report`; de vaste stijl in
  `static/src/scss/layout_tectora.scss` (bundel `web.report_assets_common`).
* De offerte-pdf van Dakmeting heeft eigen dossierstijlen; kies daar
  *Standaard Odoo-document* om ook die met deze lay-out te printen.
