# -*- coding: utf-8 -*-
META = {
    "part": "Manuali i përdorimit (Shqip)",
    "title": "Tectora Dakmeting",
    "subtitle": "Manual për matjen, ofertimin, planifikimin dhe ndjekjen e çative të sheshta në Odoo",
    "for": "Përgatitur nga Data Forge për Tectora",
    "version": "Versioni 19.0.3.7 — shtator 2026",
    "toc": "Përmbajtja",
    "tip": "Këshillë",
    "note": "Kujdes",
}

CHAPTERS = [
    ("Hyrje", [
        ("p", "Tectora Dakmeting është një shtesë e Odoo 19 me të cilën matni çati të sheshta mbi një foto satelitore ose një plan, caktoni produkte për sipërfaqet, skajet, qoshet dhe bashkimet (naden) e matura, "
              "dhe prej tyre krijoni një ofertë me një klikim. Klientët, produktet, ofertat, faturimi dhe TVSH-ja mbeten në aplikacionet standarde të Odoo; Dakmeting shton vetëm pjesën për çatitë."),
        ("p", "Aplikacioni përbëhet nga katër module që punojnë së bashku:"),
        ("ul", [
            "<b>Dakmeting</b> (tectora_roof): vizatimi, matja, projektet e çatisë, ofertat, përgatitja e kantierit dhe paneli i projektit.",
            "<b>Dakmeting — Planning</b> (tectora_roof_planning): lidh blloqet e punës së një projekti çatie me aplikacionin Planning, që çdo anëtar i ekipit të marrë turnin e vet.",
            "<b>Katalogu i produkteve</b> (tectora_products): katalogu i furnitorëve, listat e çmimeve (Renovatie, Nieuwbouw, Industrie) dhe njëzet modele ofertash.",
            "<b>Listat e materialeve</b> (tectora_boms): listat e materialeve të punimeve, prej të cilave ndërtohet lista e materialeve pas konfirmimit.",
        ]),
        ("h2", "Filli kryesor"),
        ("p", "Një <b>projekt çatie</b> qëndron gjithmonë përballë një <b>oferte/porosie</b>. Çfarë matni në vizatim shfaqet në ofertë; çfarë shtoni në ofertë shfaqet në projektin e çatisë. "
              "Me <b>konfirmimin</b> e porosisë krijohet një <b>projekt</b> i planifikueshëm me një panel ku bashkohen të ardhurat, kostot, dërgesat, detyrat dhe planifikimi."),
        ("table", [["Hapi", "Ku", "Rezultati"],
                   ["1. Matja", "Projekti i çatisë → skeda Tekening", "Seksione çatie, objekte çatie dhe bashkime me sipërfaqe dhe perimetër"],
                   ["2. Zgjedhja e produkteve", "Etiketat në vizatim, skedat e kapitujve", "Rreshta produktesh me sasi nga matja"],
                   ["3. Oferta", "Offerte maken / Shitje", "Ofertë që ndjek matjen"],
                   ["4. Konfirmimi", "Porosia e shitjes", "Projekt, listë materialesh, statusi Order bevestigd"],
                   ["5. Ekzekutimi", "Paneli i projektit, Planning", "Planifikimi i ekipit, dërgesat, orët e punës, kalkulimi përfundimtar"]]),
    ]),
    ("Fillimi", [
        ("h2", "Cilësimet"),
        ("ul", [
            "Shkoni te <b>Cilësimet → Tectora Dakmeting</b> dhe vendosni një <b>çelës API të Google Maps</b> (Geocoding + Static Maps) ose një <b>token Mapbox</b>. Pa çelës mund të vizatoni ende mbi një plan të ngarkuar.",
            "Për TVSH-në belge instaloni lokalizimin belg (l10n_be) dhe përdorni një pozicion fiskal për tarifën 6% të rinovimit.",
            "Te <b>Shitje → Produkte → Kategoritë e produkteve</b> kontrolloni fushën <b>Kan gebruikt worden voor</b>: ajo cakton cilat kategori ofron vizatimi për objektet e çatisë, skajet, sipërfaqet, qoshet dhe bashkimet.",
        ]),
        ("h2", "Menutë"),
        ("ul", [
            "<b>Dakmeting</b>: Dakprojecten, Projecten (panelet), Werkblokken, Dakobjecten, Materiaalbehoefte, Producten, Instellingen.",
            "<b>Shitje</b>: çdo ofertë mban një projekt çatie; butonat Dakproject dhe Projectdashboard qëndrojnë sipër.",
            "<b>Project</b>: klikimi mbi një projekt hap panelin e tij.",
            "<b>Punonjësit → Konfigurimi → Ploegen</b>: ekipet; vetë ekipi vendoset në kartelën e punonjësit.",
        ]),
        ("h2", "Të drejtat"),
        ("p", "Shitësit (grupi Shitje) mund të krijojnë dhe ndryshojnë projekte çatie; përdoruesit e tjerë të brendshëm mund t'i lexojnë. Përdoruesit e projektit shohin panelet, menaxherët e projektit rentabilitetin."),
    ]),
    ("Krijimi i një projekti çatie", [
        ("p", "Ka tri pika nisjeje. Të treja çojnë te i njëjti çift projekt çatie + ofertë."),
        ("ul", [
            "<b>Nga CRM</b>: në një mundësi shitjeje klikoni <b>Dakproject maken</b>. Klienti dhe adresa merren automatikisht. Një ofertë e bërë më vonë për atë mundësi lidhet vetë me këtë projekt çatie.",
            "<b>Nga Shitjet</b>: krijoni një ofertë si gjithmonë (edhe me një model oferte). Me ruajtjen krijohet automatikisht një projekt çatie me klientin, adresën e dërgesës si adresë kantieri, shitësin si drejtues projekti dhe llojin e projektit nga lista e çmimeve.",
            "<b>Nga Dakmeting</b>: <b>Dakprojecten → I ri</b>. Zgjidhni klientin, llojin e projektit dhe adresën e kantierit, vizatoni dhe klikoni <b>Offerte maken</b>.",
        ]),
        ("h2", "Fushat e projektit të çatisë"),
        ("table", [["Fusha", "Kuptimi"],
                   ["Klienti, mundësia", "Sinkronizuar me ofertën"],
                   ["Lloji i projektit", "Renovatie / Nieuwbouw / Industrie; cakton listën e çmimeve të ofertës"],
                   ["Adresa e kantierit", "Adresa që gjeokodohet për imazhin satelitor"],
                   ["Ekipi, Planifikuar", "Ekipi dhe periudha; së bashku krijojnë automatikisht një bllok pune"],
                   ["Offerte / Order", "Porosia e vetme e këtij projekti çatie (historiku përmes butonit)"],
                   ["Project", "Projekti i planifikueshëm, i krijuar me konfirmimin"]]),
        ("p", "Statusi ndjek punën: Concept → Opgemeten → Offerte gemaakt → Order bevestigd → Afgerond."),
        ("tip", "Ruajeni një projekt të ri çatie para se të vizatoni: seksionet krijohen në server dhe kanë nevojë për projektin."),
    ]),
    ("Vizatimi", [
        ("h2", "Sfondi"),
        ("p", "Ikona e globit në shiritin e mjeteve mbledh gjithçka rreth sfondit: <b>Satellietbeeld ophalen</b> (adresa e kantierit gjeokodohet, shkalla del nga projeksioni i hartës), "
              "<b>Eigen plan uploaden</b>, shfaq/fshih, tejdukshmëria dhe <b>Achtergrond verwijderen</b>."),
        ("h2", "Vizatimi i seksioneve"),
        ("ul", [
            "<b>Rechthoek</b>: tërhiqni një drejtkëndësh. <b>Polygoon</b>: klikoni qoshet dhe mbyllni me dopio-klik, Enter ose një klik në pikën e parë.",
            "<b>Selecteer</b>: klikoni për të zgjedhur, tërhiqni një formë të zgjedhur për ta zhvendosur, tërhiqni një qoshe për ta riformësuar, dopio-klik për ta riemëruar, Delete për ta hequr.",
            "<b>Pan</b> dhe rrotullimi për të lëvizur; <b>F</b> për ekran të plotë, <b>Raster</b> për një rrjetë matëse.",
        ]),
        ("h2", "Objektet e çatisë"),
        ("p", "Klikoni me të djathtën në vizatim për të shtuar një oxhak, kupolë ose objekt tjetër çatie (drejtkëndësh ose rreth). Një seksion mund të shndërrohet edhe në oxhak ose kupolë nga skeda Daksecties."),
        ("h2", "Bashkimet (naden)"),
        ("p", "Një <b>bashkim</b> (naad) tregon që dy sipërfaqe çatie janë të ndara. Zgjidhni mjetin <b>Naad</b>, klikoni pikat dhe mbyllni me dopio-klik ose Enter. "
              "Bashkimi shfaqet si vijë me pika; etiketa e tij tregon gjatësinë dhe hap zgjedhësin e produkteve me kategoritë e shënuara për <b>Naden</b>."),
        ("h2", "Kalibrimi i shkallës"),
        ("p", "Klikoni me të djathtën mbi një etiketë gjatësie dhe vendosni gjatësinë e matur realisht. Vizatimi nuk lëviz, shkalla rillogaritet. Kështu sillet në shkallë edhe një plan i ngarkuar."),
        ("h2", "Skajet dhe ngritjet"),
        ("p", "Në panelin djathtas vendosni për çdo anë një <b>gjerësi skaji</b> dhe një <b>lartësi ngritjeje</b> (butoni <b>Overal</b> për të gjitha anët). "
              "Përmasa e brendshme dhe sipërfaqja e ngritjes llogariten dhe shfaqen si vijë e brendshme me pika."),
        ("h2", "Përditësimi i matjes"),
        ("p", "Matja përditësohet automatikisht me çdo ndryshim. Butoni <b>Meting bijwerken uit tekening</b> bën të njëjtën gjë me dorë. "
              "Seksionet dhe objektet njihen nga id-ja e tyre në kanavacë, kështu që produktet e caktuara ruhen."),
    ]),
    ("Caktimi i produkteve në vizatim", [
        ("p", "Klikoni mbi një etiketë për të caktuar produkte. Çdo lloj etikete ka kategoritë e veta të produkteve (fusha <b>Kan gebruikt worden voor</b> në kategori):"),
        ("table", [["Etiketa", "Përdorimi", "Sasia"],
                   ["Emri i seksionit", "Sipërfaqja", "Sipërfaqja në m²"],
                   ["Gjatësia në një anë", "Skajet", "Gjatësia e asaj ane në m"],
                   ["Qoshja (e bardhë = e jashtme, portokalli = e brendshme)", "Qoshet", "1 copë"],
                   ["Emri i një objekti çatie", "Objektet e çatisë", "Sipërfaqja ose 1"],
                   ["Etiketa mbi një bashkim", "Bashkimet", "Gjatësia e bashkimit në m"]]),
        ("ul", [
            "<b>Disa njëherësh</b>: mbani shtypur Ctrl dhe klikoni disa anë, sipërfaqe ose qoshe të të njëjtit lloj; lëshoni Ctrl dhe zgjedhësi hapet një herë për të gjitha.",
            "Paneli djathtas liston rreshtat e formës së zgjedhur me totalin; një rresht hiqet me ikonën e koshit.",
            "Sasitë ndjekin matjen: ndryshoni formën dhe sasitë dhe oferta ndryshojnë bashkë me të.",
        ]),
    ]),
    ("Skedat e kapitujve dhe rreshtat e ofertës", [
        ("p", "Nën vizatim qëndrojnë kapitujt e ofertës. Ata pasqyrojnë rreshtat e ofertës që nuk vijnë nga vizatimi."),
        ("ul", [
            "<b>Algemene werken</b> dhe <b>Veiligheid</b>: një listë kontrolli me të gjitha produktet e kapitullit; shënimi vendos produktin në ofertë.",
            "<b>Afbraak</b>, <b>Opbouw</b> dhe <b>Overige</b>: vetëm produktet që janë në ofertë, me një rresht <b>Shto</b> që ofron vetëm produktet e atij kapitulli.",
        ]),
        ("p", "Sasia ndjek njësinë e produktit: një produkt në <b>m²</b> merr sipërfaqen totale të çatisë, një produkt në <b>m</b> perimetrin total, një produkt i numëruar (copë, shumë fikse, ditë) numrin që vendosni ju. "
              "Një produkt që vizatimi e çmon vetë (në një seksion ose objekt) zhduket nga skedat e kapitujve, që asgjë të mos numërohet dy herë."),
        ("tip", "Shtoni një rresht në ofertë dhe ai shfaqet në skedën e kategorisë së tij. Hiqeni këtu dhe zhduket edhe nga oferta, dhe anasjelltas."),
    ]),
    ("Oferta dhe porosia e shitjes", [
        ("h2", "Një me një"),
        ("p", "Çdo projekt çatie ka një ofertë/porosi dhe çdo porosi një projekt çatie. Butonat <b>Offerte / Order</b> (në projektin e çatisë) dhe <b>Dakproject</b> (në porosi) janë gjithmonë aty; nëse mungon pala tjetër, e krijojnë."),
        ("h2", "Krijimi dhe përditësimi i ofertës"),
        ("ul", [
            "<b>Offerte maken</b> në projektin e çatisë krijon ofertën me një titull për çdo seksion dhe objekt çatie, rreshtat e kapitujve nën kapitullin e tyre dhe listën e çmimeve të llojit të projektit.",
            "<b>Offerte bijwerken uit meting</b> përputh një ofertë të hapur me matjen; rreshtat manualë mbeten.",
            "Një porosi e <b>konfirmuar</b> nuk ndryshohet më kurrë. Një porosi e <b>anuluar</b> mbetet në historik dhe i lë vendin një oferte të re.",
        ]),
        ("h2", "Modelet e ofertave"),
        ("p", "Zgjidhni një model në Shitje (p.sh. Renovatie plat dak, PIR 12 cm, EPDM). Rreshtat e modelit bëhen rreshta kapitujsh në projektin e çatisë; sasitë në m² dhe m zëvendësohen menjëherë me sipërfaqen dhe perimetrin e matur."),
        ("h2", "Fushat e sinkronizuara"),
        ("table", [["Oferta", "Projekti i çatisë"],
                   ["Klienti", "Klienti"],
                   ["Mundësia", "Mundësia"],
                   ["Shitësi", "Drejtuesi i projektit"],
                   ["Data e dërgesës", "Afati"],
                   ["Lista e çmimeve", "Lloji i projektit"]]),
        ("p", "Çfarë ndryshoni në një anë shfaqet në tjetrën. Klienti dhe lista e çmimeve ndryshohen vetëm në një ofertë të hapur."),
        ("note", "Fleta e matjes shtohet automatikisht si faqe shtesë në PDF-në e ofertës."),
    ]),
    ("Përgatitja e kantierit dhe printimi", [
        ("p", "Skeda <b>Werf</b> mban fletën e kantierit: drejtimi i projektit dhe kontakti në kantier, përgatitja (Checkin@work, azbesti, lartësia, nënshtresa), aksesi për materialet dhe kantierin, transporti dhe mbetjet, "
              "shtesat (skela, platforma ngritëse, shpimi i betonit, HVAC, masat paraprake), pajisjet në vend, skajet e çatisë dhe membranat EPDM me sipërfaqen e tyre totale."),
        ("p", "Pyetjet po/jo janë kuti shënimi: e shënuar do të thotë <b>Po</b>."),
        ("h2", "Printimi"),
        ("ul", [
            "<b>Meetblad dakmeting</b>: vizatimi me përmasat dhe rreshtat e produkteve për seksion.",
            "<b>Projectinformatie werfblad</b>: fleta e plotësuar e kantierit për ekipin.",
        ]),
    ]),
    ("Konfirmimi: projekti dhe paneli", [
        ("p", "Me <b>konfirmimin</b> e porosisë ndodh automatikisht:"),
        ("ul", [
            "Krijohet një <b>projekt</b> i planifikueshëm (Odoo Project), i emëruar sipas klientit dhe komunës së kantierit, me llogarinë e vet analitike. Porosia dhe projekti tregojnë njëri-tjetrin.",
            "Ndërtohet <b>lista e materialeve</b> nga listat e materialeve të produkteve të shitura.",
            "Projekti i çatisë kalon në <b>Order bevestigd</b>.",
        ]),
        ("h2", "Paneli"),
        ("p", "Klikimi mbi një projekt (aplikacioni Project ose Dakmeting → Projecten) hap panelin. Çdo kartë hap regjistrimet pas saj:"),
        ("table", [["Karta", "Përmbajtja", "Hap"],
                   ["Omzet", "Porosia pa TVSH, e faturuar / për faturim", "Rentabiliteti"],
                   ["Kosten", "Të gjitha kostot në llogarinë analitike (të regjistruara / të pritshme)", "Rentabiliteti"],
                   ["Marge", "Të ardhurat minus kostot, në € dhe %", "Rentabiliteti"],
                   ["Materiaalkost", "Lista e materialeve × çmimi i kostos", "Lista e materialeve"],
                   ["Inkoop", "Porositë e blerjes në projekt", "Porositë e blerjes"],
                   ["Urenstaten", "Orët dhe kostoja e punës", "Orët e punës"],
                   ["Facturen", "Numri dhe shuma e papaguar", "Faturat"],
                   ["Leveringen", "Për dërgim / pjesërisht / dërguar", "Dërgesat"],
                   ["Taken", "Detyra të hapura dhe të mbyllura", "Detyrat"],
                   ["Planning", "Dita e ardhshme e punës, ekipi, orët e planifikuara, punonjësit", "Planifikimi"]]),
        ("p", "Butonat <b>Offerte / Order</b> dhe <b>Dakproject</b> janë gjithmonë të disponueshëm. Skeda <b>Dakmeting</b> tregon matjen (vizatimi, sipërfaqja, perimetri, seksionet); "
              "skedat <b>Planning</b>, <b>Taken</b> dhe <b>Materiaallijst</b> detajet. <b>Projectinstellingen</b> hap formularin standard të projektit."),
    ]),
    ("Ekipet dhe planifikimi", [
        ("h2", "Ekipet"),
        ("p", "Një ekip (ploeg) është një grup i qëndrueshëm punonjësish me një kryepunëtor. Ekipi vendoset në <b>kartelën e punonjësit</b> (skeda Punë → Ploeg); vetë ekipet menaxhohen te <b>Punonjësit → Konfigurimi → Ploegen</b>. "
              "Aplikacioni Punonjësit hapet sipas ekipit: tërhiqni një punonjës në një kolonë tjetër për t'i ndryshuar ekipin."),
        ("h2", "Planifikimi"),
        ("ul", [
            "Në projektin e çatisë zgjidhni një <b>ekip</b> dhe <b>fillimin dhe mbarimin e planifikuar</b>. Krijohet automatikisht një <b>bllok pune</b> me të gjithë anëtarët e ekipit.",
            "<b>Splits per dag</b> e ndan një bllok shumëditor në një bllok për çdo ditë; çdo bllok mund të marrë punonjësit e vet.",
            "Me aplikacionin Planning çdo punonjës bëhet një <b>turn</b> i vërtetë. Në planifikuesin <b>Per ploeg</b> zgjidhni një projekt çatie dhe një ekip në një turn dhe planifikohet gjithë ekipi.",
            "Datat e projektit të çatisë dhe të projektit ndjekin njëra-tjetrën; paneli tregon ditën e ardhshme të punës dhe punonjësit e planifikuar.",
        ]),
    ]),
    ("Lista e materialeve dhe kalkulimi përfundimtar", [
        ("p", "Me konfirmimin çdo produkt i shitur zbërthehet përmes <b>listës së materialeve</b> (përfshirë kompletet e ndërthurura) në materiale; një mall pa listë është vetë materiali, një shërbim pa listë është punë dore. "
              "Rreshtat manualë ruhen; rreshtat nga një konfirmim i mëparshëm i së njëjtës porosi zëvendësohen."),
        ("p", "Kalkulimi përfundimtar kalon përmes llogarisë analitike të projektit: faturat e klientëve, faturat e furnitorëve, porositë e blerjes, lëvizjet e stokut dhe orët e punës bashkohen aty. "
              "Paneli tregon të ardhurat, kostot dhe marzhin; karta hap analizën e detajuar të rentabilitetit të Odoo."),
    ]),
    ("Pyetje të shpeshta", [
        ("h2", "Imazhi satelitor nuk merret"),
        ("p", "Kontrolloni çelësin API te Cilësimet → Tectora Dakmeting dhe adresën e kantierit. Pa çelës mund të ngarkoni planin tuaj dhe të kalibroni shkallën me klik të djathtë mbi një gjatësi ane."),
        ("h2", "Nuk mund të caktoj produkte"),
        ("p", "Projekti i çatisë duhet të jetë i ruajtur. Nëse zgjedhësi është bosh, asnjë kategori produkti nuk e ka të shënuar përdorimin e asaj etikete (sipërfaqe, skaje, qoshe, objekte çatie, bashkime)."),
        ("h2", "Oferta nuk përputhet më me vizatimin"),
        ("p", "Klikoni <b>Offerte bijwerken uit meting</b>. Një porosi e konfirmuar nuk ndryshohet: anulojeni dhe bëni një ofertë të re, ose ndryshoni vetë porosinë."),
        ("h2", "Nuk shfaqet projekt pas konfirmimit"),
        ("p", "Klikoni <b>Projectdashboard</b> në porosi: një porosi e konfirmuar pa projekt merr një të tillë. Në rast mesazhi gabimi, shikoni regjistrin e serverit."),
        ("h2", "Një punonjës mungon në planifikim"),
        ("p", "Kontrolloni që punonjësi ka një ekip (kartela e punonjësit, skeda Punë) dhe një resurs (aplikacioni Planning). Kryepunëtori përfshihet gjithmonë."),
    ]),
]
