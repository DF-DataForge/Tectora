# Data Forge Dakmeting — Contacttype

Een **Contacttype** op elk contact (Contacten), om de contacten in te delen:

- Particulieren
- Energiehuizen
- Bouwonderneming
- Architect
- Syndicus
- Niet particulieren
- Steden en gemeentes

Het veld staat boven de labels op het contactformulier, is een kolom van de
contactenlijst (optioneel te verbergen), en je kunt erop zoeken en groeperen
(*Groeperen op › Contacttype*). Wijzigingen staan in de chatter.

## Waarom een aparte module

Een veld op `res.partner` wordt bij elke aanvraag gelezen. Toen het
Contacttype in `tectora_roof` zat (DF-DataForge/Tectora#55), draaide staging de
nieuwe code zonder module-upgrade en faalde elke pagina op de ontbrekende
kolom `res_partner.df_cont_type`.

Daarom zit het in een eigen module die **met de hand geïnstalleerd** wordt
(geen `auto_install`):

- zolang de module niet geïnstalleerd is, doet haar code niets: een deploy of
  de upgrade van de andere modules raakt de contacten niet aan;
- de installatie maakt de kolom en de schermen in één keer aan.

## Installeren

Na de deploy: *Apps* → filter *Apps* weghalen → zoek **Contacttype** →
*Activeren*. Of op de server:

```bash
cd /var/odoo/<instance>
sudo -u odoo venv/bin/python3 src/odoo-bin -c odoo.conf -d <database> \
    -i tectora_contact_type --stop-after-init
```

Daarna Odoo herstarten.
