# -*- coding: utf-8 -*-
META = {
    "part": "Handleiding (Nederlands)",
    "title": "Tectora Dakmeting",
    "subtitle": "Handleiding voor het meten, offreren, plannen en opvolgen van platte daken in Odoo",
    "for": "Opgesteld door Data Forge voor Tectora",
    "version": "Versie 19.0.3.7 — september 2026",
    "toc": "Inhoud",
    "tip": "Tip",
    "note": "Let op",
}

CHAPTERS = [
    ("Inleiding", [
        ("p", "Tectora Dakmeting is een uitbreiding van Odoo 19 waarmee u platte daken opmeet op een satellietfoto of plan, "
              "producten toewijst aan de gemeten oppervlakken, randen, hoeken en naden, en daaruit in één klik een offerte maakt. "
              "Klanten, producten, offertes, facturatie en btw blijven de standaard Odoo-apps; Dakmeting voegt alleen het dakspecifieke deel toe."),
        ("p", "De app bestaat uit vier modules die samenwerken:"),
        ("ul", [
            "<b>Dakmeting</b> (tectora_roof): tekening, meting, dakprojecten, offertes, werfvoorbereiding en het projectdashboard.",
            "<b>Dakmeting — Planning</b> (tectora_roof_planning): koppelt de werkblokken van een dakproject aan de Planning-app, zodat elke ploegmedewerker een eigen shift krijgt.",
            "<b>Productcatalogus</b> (tectora_products): de leverancierscatalogus, prijslijsten (Renovatie, Nieuwbouw, Industrie) en twintig offertesjablonen.",
            "<b>Stuklijsten</b> (tectora_boms): de stuklijsten van de werkitems, waaruit bij bevestiging de materiaallijst wordt opgebouwd.",
        ]),
        ("h2", "De rode draad"),
        ("p", "Eén <b>dakproject</b> staat altijd tegenover één <b>offerte/order</b>. Wat u op de tekening meet, verschijnt op de offerte; "
              "wat u op de offerte toevoegt, verschijnt op het dakproject. Bij het <b>bevestigen</b> van de order ontstaat een planbaar <b>project</b> "
              "met een dashboard waarop omzet, kosten, leveringen, taken en planning samenkomen."),
        ("table", [["Stap", "Waar", "Resultaat"],
                   ["1. Opmeten", "Dakproject → tab Tekening", "Daksecties, dakobjecten en naden met oppervlakte en omtrek"],
                   ["2. Producten kiezen", "Labels op de tekening, hoofdstuktabs", "Productlijnen met hoeveelheden uit de meting"],
                   ["3. Offerte", "Offerte maken / Verkoop", "Offerte die de meting volgt"],
                   ["4. Bevestigen", "Verkooporder", "Project, materiaallijst, status Order bevestigd"],
                   ["5. Uitvoeren", "Projectdashboard, Planning", "Ploegplanning, leveringen, urenstaten, nacalculatie"]]),
    ]),
    ("Aan de slag", [
        ("h2", "Instellingen"),
        ("ul", [
            "Ga naar <b>Instellingen → Tectora Dakmeting</b> en vul een <b>Google Maps API-sleutel</b> (Geocoding + Static Maps) of een <b>Mapbox-token</b> in. Zonder sleutel kunt u nog altijd tekenen op een geüpload plan.",
            "Installeer voor Belgische btw de Belgische lokalisatie (l10n_be) en gebruik een fiscale positie voor het 6%-tarief bij renovatie.",
            "Controleer onder <b>Verkoop → Producten → Productcategorieën</b> het veld <b>Kan gebruikt worden voor</b>: dat bepaalt welke categorieën de tekening aanbiedt voor dakobjecten, randen, oppervlaktes, hoeken en naden.",
        ]),
        ("h2", "Menu's"),
        ("ul", [
            "<b>Dakmeting</b>: Dakprojecten, Projecten (dashboards), Werkblokken, Dakobjecten, Materiaalbehoefte, Producten, Instellingen.",
            "<b>Verkoop</b>: elke offerte draagt een dakproject; de smart buttons Dakproject en Projectdashboard staan bovenaan.",
            "<b>Project</b>: klikken op een project opent het projectdashboard.",
            "<b>Werknemers → Configuratie → Ploegen</b>: de ploegen; de ploeg zelf staat op de werknemersfiche.",
        ]),
        ("h2", "Rechten"),
        ("p", "Verkopers (groep Verkoop) mogen dakprojecten aanmaken en bewerken; andere interne gebruikers kunnen ze lezen. "
              "Projectgebruikers zien de dashboards, projectmanagers de winstgevendheid."),
    ]),
    ("Een dakproject aanmaken", [
        ("p", "Er zijn drie startpunten. Ze leiden alle drie tot hetzelfde paar dakproject + offerte."),
        ("ul", [
            "<b>Vanuit CRM</b>: op een opportuniteit klikt u <b>Dakproject maken</b>. Klant en adres worden overgenomen. Maakt u nadien een offerte op die opportuniteit, dan koppelt die zich automatisch aan dit dakproject.",
            "<b>Vanuit Verkoop</b>: maak een offerte zoals altijd (eventueel met een offertesjabloon). Bij het opslaan ontstaat automatisch een dakproject met de klant, het leveradres als werfadres, de verkoper als projectleider en het projecttype uit de prijslijst.",
            "<b>Vanuit Dakmeting</b>: <b>Dakprojecten → Nieuw</b>. Kies klant, projecttype en werfadres, teken en klik <b>Offerte maken</b>.",
        ]),
        ("h2", "Velden op het dakproject"),
        ("table", [["Veld", "Betekenis"],
                   ["Klant, opportuniteit", "Gesynchroniseerd met de offerte"],
                   ["Projecttype", "Renovatie / Nieuwbouw / Industrie; bepaalt de prijslijst van de offerte"],
                   ["Werfadres", "Adres dat gegeocodeerd wordt voor het satellietbeeld"],
                   ["Ploeg, Gepland", "Ploeg en periode; samen maken ze automatisch een werkblok aan"],
                   ["Offerte / Order", "De ene order van dit dakproject (historiek via de smart button)"],
                   ["Project", "Het planbare project, aangemaakt bij bevestiging"]]),
        ("p", "De status volgt het werk: Concept → Opgemeten → Offerte gemaakt → Order bevestigd → Afgerond."),
        ("tip", "Sla een nieuw dakproject eerst op voordat u tekent: de secties worden op de server aangemaakt en hebben het project nodig."),
    ]),
    ("De tekening", [
        ("h2", "Achtergrond"),
        ("p", "Het wereldbol-icoon in de werkbalk bundelt alles rond de achtergrond: <b>Satellietbeeld ophalen</b> (het werfadres wordt gegeocodeerd, de schaal volgt uit de kaartprojectie), "
              "<b>Eigen plan uploaden</b>, tonen/verbergen, transparantie en <b>Achtergrond verwijderen</b>."),
        ("h2", "Secties tekenen"),
        ("ul", [
            "<b>Rechthoek</b>: sleep een rechthoek. <b>Polygoon</b>: klik de hoekpunten en sluit met dubbelklik, Enter of een klik op het eerste punt.",
            "<b>Selecteer</b>: klik om te selecteren, sleep een geselecteerde vorm om te verplaatsen, versleep een hoekpunt om de vorm aan te passen, dubbelklik om te hernoemen, Delete om te verwijderen.",
            "<b>Pan</b> en scrollen om te navigeren; <b>F</b> voor volledig scherm, <b>Raster</b> voor een meetraster.",
        ]),
        ("h2", "Dakobjecten"),
        ("p", "Rechtsklik op de tekening om een schoorsteen, koepel of ander dakobject toe te voegen (rechthoek of cirkel). Een sectie kan ook omgezet worden naar een schoorsteen of koepel via de tab Daksecties."),
        ("h2", "Naden"),
        ("p", "Een <b>naad</b> geeft aan dat twee dakvlakken gescheiden zijn. Kies de tool <b>Naad</b>, klik de punten en sluit af met dubbelklik of Enter. "
              "De naad verschijnt als stippellijn; het label toont de lengte en opent de productkiezer met de categorieën die voor <b>Naden</b> zijn aangevinkt."),
        ("h2", "Schaal kalibreren"),
        ("p", "Rechtsklik op een lengtelabel en geef de werkelijk gemeten lengte in. De tekening beweegt niet, de schaal wordt herrekend. "
              "Dat is ook de manier om een geüpload plan op maat te brengen."),
        ("h2", "Randen en opstanden"),
        ("p", "In het paneel rechts stelt u per zijde een <b>randbreedte</b> en een <b>opstandhoogte</b> in (knop <b>Overal</b> voor alle zijden). "
              "De binnenmaat en de opstandoppervlakte worden meegerekend en tonen als gestippelde binnenlijn."),
        ("h2", "Meting bijwerken"),
        ("p", "De meting wordt automatisch bijgewerkt bij elke wijziging. De knop <b>Meting bijwerken uit tekening</b> doet hetzelfde handmatig. "
              "Secties en objecten worden herkend aan hun canvas-id, zodat toegewezen producten bewaard blijven."),
    ]),
    ("Producten toewijzen op de tekening", [
        ("p", "Klik op een label om producten toe te wijzen. Elk labeltype heeft zijn eigen productcategorieën (veld <b>Kan gebruikt worden voor</b> op de categorie):"),
        ("table", [["Label", "Toepassing", "Hoeveelheid"],
                   ["Naam van de sectie", "Oppervlak", "Oppervlakte in m²"],
                   ["Lengte op een zijde", "Randen", "Lengte van die zijde in m"],
                   ["Hoekpunt (wit = buitenhoek, oranje = binnenhoek)", "Hoeken", "1 stuk"],
                   ["Naam van een dakobject", "Dakobjecten", "Oppervlakte of 1"],
                   ["Label op een naad", "Naden", "Lengte van de naad in m"]]),
        ("ul", [
            "<b>Meerdere tegelijk</b>: houd Ctrl ingedrukt en klik meerdere zijden, oppervlakken of hoeken van hetzelfde type; laat Ctrl los en de kiezer opent één keer voor allemaal.",
            "Het paneel rechts toont de lijnen van de geselecteerde vorm met totaal; een lijn verwijderen kan met het prullenbakje.",
            "Hoeveelheden volgen de meting: verandert de vorm, dan veranderen de hoeveelheden en de offerte mee.",
        ]),
    ]),
    ("Hoofdstuktabs en offertelijnen", [
        ("p", "Onder de tekening staan de hoofdstukken van de offerte. Ze zijn de spiegel van de offertelijnen die niet uit de tekening komen."),
        ("ul", [
            "<b>Algemene werken</b> en <b>Veiligheid</b>: een checklist van alle producten van het hoofdstuk; aanvinken zet het product op de offerte.",
            "<b>Afbraak</b>, <b>Opbouw</b> en <b>Overige</b>: alleen de producten die op de offerte staan, met een regel <b>Toevoegen</b> die enkel producten van dat hoofdstuk aanbiedt.",
        ]),
        ("p", "De hoeveelheid volgt de eenheid van het product: een <b>m²</b>-product neemt de totale dakoppervlakte, een <b>m</b>-product de totale omtrek, "
              "een geteld product (stuks, forfait, dagen) het aantal dat u invult. Een product dat de tekening zelf prijst (op een sectie of object) verdwijnt uit de hoofdstuktabs, zodat niets dubbel telt."),
        ("tip", "Voegt u op de offerte een lijn toe, dan verschijnt ze in de tab van haar categorie. Verwijdert u ze hier, dan verdwijnt ze ook op de offerte, en omgekeerd."),
    ]),
    ("Offerte en verkooporder", [
        ("h2", "Eén op één"),
        ("p", "Elk dakproject heeft één offerte/order en elke order één dakproject. De smart buttons <b>Offerte / Order</b> (op het dakproject) en <b>Dakproject</b> (op de order) staan er altijd; ontbreekt de tegenhanger, dan maken ze die aan."),
        ("h2", "Offerte maken en bijwerken"),
        ("ul", [
            "<b>Offerte maken</b> op het dakproject maakt de offerte met een kop per daksectie en dakobject, de hoofdstuklijnen onder hun hoofdstuk en de prijslijst van het projecttype.",
            "<b>Offerte bijwerken uit meting</b> brengt een open offerte in lijn met de meting; handmatige lijnen blijven staan.",
            "Een <b>bevestigde</b> order wordt nooit meer aangepast. Een <b>geannuleerde</b> order blijft in de historiek en maakt plaats voor een nieuwe.",
        ]),
        ("h2", "Offertesjablonen"),
        ("p", "Kies in Verkoop een sjabloon (bv. Renovatie plat dak, PIR 12 cm, EPDM). De sjabloonlijnen worden hoofdstuklijnen op het dakproject; "
              "de m²- en m-hoeveelheden worden meteen vervangen door de gemeten oppervlakte en omtrek."),
        ("h2", "Gesynchroniseerde velden"),
        ("table", [["Offerte", "Dakproject"],
                   ["Klant", "Klant"],
                   ["Opportuniteit", "Opportuniteit"],
                   ["Verkoper", "Projectleider"],
                   ["Leverdatum", "Deadline"],
                   ["Prijslijst", "Projecttype"]]),
        ("p", "Wat u op de ene kant wijzigt, verschijnt op de andere. Klant en prijslijst worden alleen nog op een openstaande offerte aangepast."),
        ("note", "Het meetblad wordt automatisch als extra pagina in de offerte-pdf opgenomen."),
    ]),
    ("Werfvoorbereiding en afdrukken", [
        ("p", "De tab <b>Werf</b> bundelt het werfblad: projectleiding en contactpersoon, voorbereiding (Checkin@work, asbest, hoogte, ondergrond), "
              "bereikbaarheid van materiaal en werf, transport en afvoer, extra's (stelling, hoogwerker, betonboring, HVAC, voorzorgsmaatregelen), voorzieningen ter plaatse, "
              "dakranden en de EPDM-doeken met hun totale oppervlakte."),
        ("p", "De ja/nee-vragen zijn aankruisvakjes: aangevinkt is <b>Ja</b>."),
        ("h2", "Afdrukken"),
        ("ul", [
            "<b>Meetblad dakmeting</b>: de tekening met maten en de productlijnen per sectie.",
            "<b>Projectinformatie werfblad</b>: het ingevulde werfblad voor de ploeg.",
        ]),
    ]),
    ("Bevestiging: project en projectdashboard", [
        ("p", "Bij het <b>bevestigen</b> van de order gebeurt automatisch:"),
        ("ul", [
            "Er wordt een planbaar <b>project</b> aangemaakt (Odoo Project), genoemd naar de klant en de gemeente van de werf, met een eigen analytische rekening. De order en het project verwijzen naar elkaar.",
            "De <b>materiaallijst</b> wordt opgebouwd uit de stuklijsten van de verkochte producten.",
            "Het dakproject gaat naar <b>Order bevestigd</b>.",
        ]),
        ("h2", "Het dashboard"),
        ("p", "Klikken op een project (Project-app of Dakmeting → Projecten) opent het dashboard. Elke kaart is doorklikbaar naar de records erachter:"),
        ("table", [["Kaart", "Inhoud", "Opent"],
                   ["Omzet", "Order excl. btw, gefactureerd / te factureren", "Winstgevendheid"],
                   ["Kosten", "Alle kosten op de analytische rekening (geboekt / verwacht)", "Winstgevendheid"],
                   ["Marge", "Omzet min kosten, in € en %", "Winstgevendheid"],
                   ["Materiaalkost", "Stuklijst × kostprijs", "Materiaallijst"],
                   ["Inkoop", "Inkooporders op het project", "Inkooporders"],
                   ["Urenstaten", "Uren en loonkost", "Urenstaten"],
                   ["Facturen", "Aantal en openstaand bedrag", "Facturen"],
                   ["Leveringen", "Te leveren / deels / geleverd", "Leveringen"],
                   ["Taken", "Open en afgeronde taken", "Taken"],
                   ["Planning", "Volgende werkdag, ploeg, geplande uren, medewerkers", "Planning"]]),
        ("p", "De smart buttons <b>Offerte / Order</b> en <b>Dakproject</b> zijn altijd beschikbaar. De tab <b>Dakmeting</b> toont de meting (tekening, oppervlakte, omtrek, daksecties); "
              "de tabs <b>Planning</b>, <b>Taken</b> en <b>Materiaallijst</b> de details. <b>Projectinstellingen</b> opent het standaard projectformulier."),
    ]),
    ("Ploegen en planning", [
        ("h2", "Ploegen"),
        ("p", "Een ploeg is een vaste groep medewerkers met een ploegbaas. De ploeg staat op de <b>werknemersfiche</b> (tab Werk → Ploeg); de ploegen zelf beheert u onder <b>Werknemers → Configuratie → Ploegen</b>. "
              "De Werknemers-app opent per ploeg: sleep een medewerker naar een andere kolom om zijn ploeg te wijzigen."),
        ("h2", "Plannen"),
        ("ul", [
            "Kies op het dakproject een <b>ploeg</b> en de <b>geplande start en einde</b>. Er ontstaat automatisch een <b>werkblok</b> met alle ploegleden.",
            "<b>Splits per dag</b> maakt van een meerdaags blok één blok per dag; elk blok kan eigen medewerkers krijgen.",
            "Met de Planning-app wordt elke medewerker een echte <b>shift</b>. In de planner <b>Per ploeg</b> kiest u een dakproject en een ploeg op één shift en de hele ploeg wordt gepland.",
            "De datums van het dakproject en het project volgen elkaar; het dashboard toont de volgende werkdag en de ingeplande medewerkers.",
        ]),
    ]),
    ("Materiaallijst en nacalculatie", [
        ("p", "Bij bevestiging wordt elk verkocht product via zijn <b>stuklijst</b> (inclusief geneste kits) ontbonden in materialen; een goed zonder stuklijst is zelf het materiaal, een dienst zonder stuklijst is arbeid. "
              "Handmatige lijnen blijven bewaard; lijnen van een eerdere bevestiging van dezelfde order worden vervangen."),
        ("p", "De nacalculatie loopt via de analytische rekening van het project: verkoopfacturen, leveranciersfacturen, inkooporders, voorraadbewegingen en urenstaten komen er samen. "
              "Het dashboard toont omzet, kosten en marge; de kaart opent de gedetailleerde winstgevendheidsanalyse van Odoo."),
    ]),
    ("Veelgestelde vragen", [
        ("h2", "Het satellietbeeld wordt niet opgehaald"),
        ("p", "Controleer de API-sleutel in Instellingen → Tectora Dakmeting en het werfadres. Zonder sleutel kunt u een eigen plan uploaden en de schaal kalibreren via rechtsklik op een zijdelengte."),
        ("h2", "Ik kan geen producten toewijzen"),
        ("p", "Het dakproject moet opgeslagen zijn. Verschijnt de kiezer leeg, dan heeft geen enkele productcategorie de toepassing van dat label (oppervlak, randen, hoeken, dakobjecten, naden) aangevinkt."),
        ("h2", "De offerte klopt niet meer met de tekening"),
        ("p", "Klik op <b>Offerte bijwerken uit meting</b>. Een bevestigde order wordt niet aangepast: annuleer ze en maak een nieuwe offerte, of pas de order zelf aan."),
        ("h2", "Er verschijnt geen project na bevestiging"),
        ("p", "Klik op <b>Projectdashboard</b> op de order: een bevestigde order zonder project krijgt er dan een. Kijk bij een foutmelding in de serverlog."),
        ("h2", "Een medewerker staat niet in de planning"),
        ("p", "Controleer of de medewerker een ploeg heeft (werknemersfiche, tab Werk) en een resource (Planning-app). De ploegbaas wordt altijd meegerekend."),
    ]),
]
