# Data Forge Dakmeting — Bestellijst op de materiaallijst

Koppelt de **Bestellijst** (`tectora_project_order_list`) aan de
**Materiaallijst** van het project (`tectora_purchase`).

| Op de bestellijst | Op de materiaallijst |
|---|---|
| Producten **Bestellen** bij een leverancier | de materiaallijn krijgt de inkooplijn: **Inkooporder**, **Leverancier** en **Inkoopstatus** (Offerteaanvraag → Besteld → Ontvangen) volgen die bestelling |
| Producten **Leveren vanuit stock** | de materiaallijn staat op **Uit voorraad**, met de uitgaande levering (WH/OUT/…) en haar status |

* Een materiaallijn die al op een inkooporder staat (bv. via **Inkooporders
  aanmaken** op de materiaallijst) houdt die bestelling.
* Een geannuleerde bestelling of levering zet de lijn terug op **Te bestellen**.
* Installeert zichzelf zodra de Bestellijst en Dakmeting — Inkoop
  geïnstalleerd zijn.
