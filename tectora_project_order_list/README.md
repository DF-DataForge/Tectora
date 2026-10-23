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

## On the project

- A **new project** gets an order list with one line per part. Existing
  projects create theirs with **Bestellijst aanmaken** on the dashboard.
- **Dashboard**: the block *Bestellijst* shows the progress and the next parts
  to order (tick them off in place); *Openen* opens the order list page.
- **Order list page**: per line tick off, supplier, order date, expected
  delivery date, status and **Bestellen**, which creates a request for
  quotation for the line's products, charged to the project (*Stock eerst*:
  only the shortage). Filter *Enkel open*, *Lijstweergave* for the editable list.
- The line's status follows its purchase orders: te bestellen, uit stock,
  prijsaanvraag, besteld, ontvangen, afgevinkt; a line whose expected delivery
  date has passed shows *te laat*.
- *Dakmeting › Bestellijst* lists the open lines of all projects, per project
  or per supplier.
