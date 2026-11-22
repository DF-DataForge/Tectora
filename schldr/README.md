# Schldr

Schilderplanner voor Odoo 20: teken de ruimtes van een woning in 2D, geef ze een
plafondhoogte, en Schldr rekent elke muur, elk plafond, elke vloer en al het
houtwerk uit. Op die oppervlakken zet je verfsystemen (grondlaag, tussenlaag,
eindlagen), waaruit de offerte, de order, het project en de materiaallijst
per kleur volgen.

Schldr is een afsplitsing van de Tectora-modules (DF-DataForge/Tectora, commit
`f9e8309`): de flow van offerte tot project en het medewerkersportaal zijn
overgenomen, het tekenen en rekenen is nieuw. `tools/port_from_tectora.py` deed
het mechanische deel van die afsplitsing.

## Modules

| Module | Wat |
|---|---|
| `schldr_paint` | De toepassing: plan, oppervlakken, verfsystemen, offerte, project, materiaallijst |
| `schldr_portal` | Medewerkersportaal: werven, kleurenstaat per ruimte, uren, uitvoeringsverslagen |
| `schldr_quote_builder` | Kop- en voetteksten (pdf) in de offerte |
| `schldr_report_layout` | Documentlay-out en briefpapier |
| `schldr_contact_type` | Contacttype op contacten (met de hand te installeren) |

Nog niet overgenomen uit de oorspronkelijke planner: inkoop en logistiek,
voorraad, ploegplanning met weer, taken per fase, bestellijst per project en
de Excel-import van offertes.

## Rekenen

`schldr_paint/lib/` is gewone Python zonder Odoo:

* `document.py` — het plandocument (JSON, millimeters, vaste id's per onderdeel);
* `geometry.py` — veelhoeken knippen en meten;
* `measure.py` — van document naar oppervlakken: muren met openingen en
  dagkanten, schuine plafonds, plinten, omlijstingen, deurbladen, radiatoren;
* `packs.py` — welke potten voor een hoeveelheid verf.

De editor in de browser heeft dezelfde code in JavaScript; beide worden tegen
dezelfde voorbeelden getest.

## Testen

De rekenkern (Python):

```bash
python3 -m pytest tests
```

Dezelfde rekenkern en de bewerkingen van de editor (JavaScript):

```bash
node --import ./tests/js/register.mjs --test tests/js/lib.test.mjs
```

Geen namen van de oorspronkelijke toepassing meer in de code:

```bash
python3 tools/check_names.py
```

De Odoo-tests (`schldr_*/tests`) draaien in een Odoo 20-database met een
rekeningschema:

```bash
odoo-bin -d <testdb> -i l10n_be,schldr_paint,schldr_portal,schldr_quote_builder,schldr_report_layout,schldr_contact_type --test-enable --test-tags /schldr_paint,/schldr_portal,/schldr_quote_builder,/schldr_report_layout,/schldr_contact_type --stop-after-init
```

`tests/fixtures/*.json` bevat plannen met wat de Python-rekenkern erin meet;
de JavaScript-tests moeten op dezelfde cijfers uitkomen. Na een bewuste
wijziging van het rekenwerk: `python3 tests/make_fixtures.py`.
