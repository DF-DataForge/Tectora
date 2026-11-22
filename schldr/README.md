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
| `schldr_paint` | De toepassing: plan, oppervlakken, verfsystemen, offerte, project |
| `schldr_report_layout` | Documentlay-out en briefpapier |
| `schldr_contact_type` | Contacttype op contacten (met de hand te installeren) |

Nog te porten: `schldr_quote_builder`, `schldr_portal`.

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

```bash
python3 -m pytest tests
```

```bash
python3 tools/check_names.py
```

De Odoo-tests (`schldr_*/tests`) draaien in een Odoo 20-database:

```bash
odoo-bin -d <testdb> -i schldr_paint --test-enable --test-tags /schldr_paint --stop-after-init
```
