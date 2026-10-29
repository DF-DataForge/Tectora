# Bestellijst (`tectora_project_order_list`)

The order list of the Congristruct project dashboard (`df_congristruct_pm`),
starting from an **empty list of standard parts**: every company configures
its own parts.

## Configuration

*Dakmeting › Projectopvolging › Bestellijst-onderdelen* (or *Project ›
Configuratie*): per part the order (longest lead time on top), the action
**Bestellen** (always order for the project) or **Stock eerst** (check the
stock, order only the shortage), the suggested suppliers (the first one is
chosen by default) and a note on them.

A task template can be marked **Bestellijst afgevinkt (automatisch)**: that
task is ticked off as soon as the whole order list is, opens again when a line
is reopened, and links to the order list on the task page.

## Importeren uit Excel

*Dakmeting › Projectopvolging › Bestellijst importeren*: download de
**standaardlijst** (`Bestellijst.xlsx`), vul ze aan en laad ze terug op.

- Tabblad **Bestellijst**, één regel per onderdeel: *Volgorde* (leeg = de
  volgorde van de regels), *Onderdeel* (verplicht), *Actie* (Bestellen of
  Stock eerst; leeg = Bestellen), *Leveranciers* (namen van contacten,
  gescheiden door `;`; de eerste is de standaardleverancier), *Toelichting
  leveranciers*.
- Een leverancier die niet als contact bestaat, wordt overgeslagen en in het
  verslag vermeld, of aangemaakt met *Ontbrekende leveranciers aanmaken*.
- *Toevoegen en bijwerken* / *Vervangen* en de foutmeldingen per rij: zoals bij
  de taaksjablonen.
- Bestaande bestellijsten van projecten veranderen niet.

## On the project

- A **new project** gets an order list with one line per part. Existing
  projects create theirs with **Bestellijst aanmaken** on the dashboard.
- **Dashboard**: the block *Bestellijst* shows the progress and the next parts
  to order (tick them off in place); *Openen* opens the order list page.
- **Order list page**: per line tick off, supplier, order date, expected
  delivery date, status and **Bestellen**, which creates a request for
  quotation for the line's products, charged to the project (*Stock eerst*:
  only the shortage). Filter *Enkel open*, *Lijstweergave* for the editable list.
- **Producten** on a line opens, under it, the products its supplier delivers
  (the supplier on the products' *Inkoop* tab; without a chosen supplier, the
  suggested ones) that are on the project's material list, with the quantity
  the list needs, and the products already on the line. **Ander product
  toevoegen** under the list searches any purchasable product (the
  supplier's first) and adds it, ticked, for what the material list does not
  cover. Every product shows its free stock.
- Once ordered, products are set apart under **Reeds in bestelling bij
  <leverancier>**, per purchase order with its status; what is not ordered
  stays on top and can go to another supplier (a cancelled order puts its
  products back).
- **Leveren vanuit stock** puts the selected products on the project's open
  outgoing delivery of the order list (a new one when there is none, to the
  site), confirmed so the warehouse stock is reserved; they show under
  **Leveren vanuit magazijn** with their reservation. With the roof project's
  transfers installed the delivery is on the roof project, so its material
  transfers do not ship them again. Tick them, set the
  quantity, and **Bestellen** puts exactly those on the request for quotation
  (they are added to the line's products too).
- The line's status follows its purchase orders: te bestellen, uit stock,
  prijsaanvraag, besteld, ontvangen, afgevinkt; a line whose expected delivery
  date has passed shows *te laat*.
- *Dakmeting › Bestellijst* lists the open lines of all projects, per project
  or per supplier.
