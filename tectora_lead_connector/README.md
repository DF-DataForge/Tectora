# Leadconnectoren (`tectora_lead_connector`)

Offerteaanvragen van leadplatformen komen via een **webhook** automatisch als
lead in de CRM, zonder overtypen. Eerste platform: **AannemerOffertes.be**.

## Instellen

1. Installeer de module (CRM › Configuratie › **Leadconnectoren**).
2. Maak een connector aan, type *AannemerOffertes.be*.
3. Kies een **ondertekeningsgeheim** (een lange willekeurige tekst) en vul het in.
4. Kies wat de leads krijgen: lead of verkoopkans, verkoopteam, verkoper,
   bron (standaard *Lead AannemerOffertes*), medium en labels.
5. Mail de **webhook-URL** (kopieerknop op het formulier) en het geheim naar
   AannemerOffertes.be.

De URL bevat een geheim token: *Nieuwe webhook-URL* maakt een nieuwe en de oude
ongeldig. Odoo moet via HTTPS bereikbaar zijn op die URL; bij meerdere databanken
op één server moet de `dbfilter` de databank uit de hostnaam halen.

## Wat de webhook doet

`POST /tectora/leads/aannemeroffertes/<token>`

| Controle | Antwoord | Platform |
|---|---|---|
| Lead aangemaakt, of de aanvraag was al verwerkt | **200** | stopt |
| Geen JSON-object of geen `id` | **406** | stopt (kan nooit lukken) |
| Handtekening ontbreekt / klopt niet, of `X-Timestamp` te oud | 401 | probeert opnieuw |
| Onbekende of gearchiveerde connector | 404 | probeert opnieuw |
| Lead kon niet aangemaakt worden (fout staat op de aanvraag) | 500 | probeert opnieuw |

De handtekening: `hex(HMAC-SHA256(geheim, X-Timestamp + X-Token)) == X-Signature`.
Zonder geheim wordt niet gecontroleerd (enkel om te testen). *Maximale
ouderdom* (standaard 24 uur, 0 = uit) weigert aanvragen met een te oude
`X-Timestamp`. Het platform blijft tot ongeveer 17 uur opnieuw proberen, dus
houd die ruim. Een aanvraag die opnieuw binnenkomt (herhaling, replay)
maakt nooit een tweede lead. Ze telt alleen mee in *Opnieuw ontvangen*.

## De lead

| Lead | Uit de aanvraag |
|---|---|
| Titel | soort werk - naam - gemeente, bv. *Nieuw huis bouwen - John Doe - Utrecht* |
| Contact | `first_name` + `last_name`, aanspreektitel uit `title` (Mr → Dhr., Mrs → Mevr.) |
| E-mail, telefoon | `email`, `phonenumber` |
| Adres | `address.address`, `postal_code`, `locality`, `dependent_locality`, `country_code` |
| Taal | `locale` (als die taal actief is) |
| Contactpersoon | een bestaand contact met hetzelfde e-mailadres |
| Notities | `description`, aanvraag-ID, soort werk, gewenste planning (`date_planned`), locatie, concurrenten, link naar de kaart |
| Bron, medium, team, verkoper, labels, type | van de connector |

De aanspreektitel staat ook op de lead (in debugmodus naast de contactnaam)
en gaat mee naar het contact dat bij het omzetten wordt aangemaakt.

## Ontvangen aanvragen

CRM › Configuratie › **Ontvangen leadaanvragen** toont elke aanvraag met haar
inhoud (JSON), status en lead. Bij een aanvraag met een fout staat de
foutmelding op de aanvraag. Met *Opnieuw verwerken* maak je de lead alsnog aan.

## Een ander platform toevoegen

Voeg een waarde toe aan `provider` op `tectora.lead.connector` en een methode
`_<provider>_lead_values(payload)` die de waarden van de lead teruggeeft. Pas
`_check_signature` aan als het platform anders ondertekent.
