# Data Forge Dakmeting — Medewerkersportaal

Portaal voor de dakwerkers. Een medewerker (`hr.employee`) krijgt een
**portaallogin** (externe gebruiker, geen backend-licentie) en vindt onder
*Mijn werven* (`/my/werven`) elke werf waarop hij ingepland is — als lid van
een werkblok of als lid/ploegbaas van de ploeg van het project.

## Toegang geven

1. Open de medewerker (Werknemers) en vul een **werk-e-mailadres** in.
2. Klik op **Portaaltoegang geven**. Er wordt een portaalgebruiker aangemaakt
   op het werkcontact van de medewerker, gekoppeld via het standaardveld
   *Gerelateerde gebruiker*, en de uitnodiging om een wachtwoord te kiezen
   wordt verstuurd (module `auth_signup`).
3. De knop wordt **Portaal actief**; de filter *Met portaaltoegang* in de
   werknemerslijst toont wie er al op zit. Een medewerker met een interne
   gebruiker gebruikt gewoon die login.

## Wat de medewerker ziet

*Mijn werven* toont de werven met volgende werkdag, ploeg en status, met de
filters *Gepland* (standaard), *Vandaag*, *Uren lopen* en *Alle werven*. Een
werf opent op vier tabs:

| Tab | Inhoud |
|---|---|
| **Overzicht** | klant, werfadres (link naar Google Maps), projecttype, status, contactpersoon werf en projectleider (bel-links), ploeg en planning, werfinstructies en notities, het **werfblad** (voorbereiding, bereikbaarheid, transport, extra's, EPDM), knoppen Werfblad- en Meetblad-pdf |
| **Materialen** | de materiaallijst van het project (product, hoeveelheid, eenheid, herkomst) |
| **Plan** | het **dakplan** (tekening, kerncijfers, daksecties en dakobjecten) en de **werkdagen** met de ingeplande medewerkers |
| **Uitvoeringsverslag** | de dagverslagen van de ploeg (uitgevoerde werken, materialen, opmerkingen, foto's) met een formulier voor een nieuw verslag, en de uren op de werf |

## Uren registreren (start/stop)

Bovenaan elke werf staat de urenregistratie:

* **Start** opent één registratie per werf (`tectora.roof.timer`). De ploeg
  van die dag wordt uit de planner gehaald: de medewerkers op het werkblok
  van vandaag, anders die van het dichtstbijzijnde werkblok, anders de leden
  van de ploeg. Wie start staat er altijd bij.
* **Stop** vraagt wie aanwezig was (vooraf aangevinkt volgens de planning)
  en een optionele nota, sluit de registratie en boekt **één urenstaatlijn
  per medewerker** (`account.analytic.line`) op het project van de order —
  dat wordt aangemaakt als de order nog niet bevestigd was. Zo komen de
  uren en de loonkost in het projectdashboard en in de standaard
  Urenstaten-rapporten terecht.
* Een registratie die niemand stopt, wordt door een cron na 16 uur gesloten
  (met nota), zodat een vergeten Stop nooit dagen uren boekt.

De registraties staan in de backend onder *Dakmeting → Urenregistraties* en
op de tab **Uitvoering** van het projectdashboard, samen met de
uitvoeringsverslagen (*Dakmeting → Uitvoeringsverslagen*). Annuleren van een
registratie verwijdert haar urenstaatlijnen.

## Technisch

* Afhankelijkheden: `tectora_roof`, `portal`, `hr_timesheet`.
* De controller (`controllers/portal.py`) zoekt de medewerker achter de
  ingelogde gebruiker en toont enkel de projecten uit
  `tectora.roof.project._tectora_portal_domain()`. Daarna wordt met `sudo`
  gelezen en geschreven, zoals de standaard portaalcontrollers met hun
  toegangstokens: de portaalgroep krijgt geen rechten op de dakmodellen.
* Foto's zijn `ir.attachment`-records op het verslag en worden via
  `/my/werven/<id>/foto/<attachment>` geserveerd na dezelfde controle.
* Routes: `/my/werven`, `/my/werven/<id>?tab=overview|materials|plan|report`,
  `POST …/uren/start`, `POST …/uren/<timer>/stop`, `POST …/verslag`,
  `…/pdf/meetblad`, `…/pdf/werfblad`.
