# -*- coding: utf-8 -*-
META = {
    "part": "User Manual (English)",
    "title": "Tectora Dakmeting",
    "subtitle": "Manual for measuring, quoting, planning and following up flat roofs in Odoo",
    "for": "Prepared by Data Forge for Tectora",
    "version": "Version 19.0.3.7 — September 2026",
    "toc": "Contents",
    "tip": "Tip",
    "note": "Note",
}

CHAPTERS = [
    ("Introduction", [
        ("p", "Tectora Dakmeting is an Odoo 19 extension for measuring flat roofs on a satellite photo or plan, assigning products to the measured surfaces, edges, corners and seams, "
              "and turning that into a quotation in one click. Customers, products, quotations, invoicing and VAT stay in the standard Odoo apps; Dakmeting only adds the roofing part."),
        ("p", "The app consists of four modules that work together:"),
        ("ul", [
            "<b>Dakmeting</b> (tectora_roof): drawing, measurement, roof projects, quotations, site preparation and the project dashboard.",
            "<b>Dakmeting — Planning</b> (tectora_roof_planning): bridges the work blocks of a roof project to the Planning app, so every team member gets a shift.",
            "<b>Product catalogue</b> (tectora_products): the supplier catalogue, pricelists (Renovatie, Nieuwbouw, Industrie) and twenty quotation templates.",
            "<b>Bills of materials</b> (tectora_boms): the bills of materials of the works items, from which the material list is built on confirmation.",
        ]),
        ("h2", "The thread"),
        ("p", "One <b>roof project</b> always stands against one <b>quotation/order</b>. What you measure on the drawing appears on the quotation; what you add on the quotation appears on the roof project. "
              "<b>Confirming</b> the order creates a plannable <b>project</b> with a dashboard where revenue, costs, deliveries, tasks and planning come together."),
        ("table", [["Step", "Where", "Result"],
                   ["1. Measure", "Roof project → Tekening tab", "Roof sections, roof objects and seams with area and perimeter"],
                   ["2. Pick products", "Labels on the drawing, chapter tabs", "Product lines with quantities from the measurement"],
                   ["3. Quote", "Offerte maken / Sales", "A quotation that follows the measurement"],
                   ["4. Confirm", "Sales order", "Project, material list, status Order bevestigd"],
                   ["5. Execute", "Project dashboard, Planning", "Team planning, deliveries, timesheets, post-calculation"]]),
    ]),
    ("Getting started", [
        ("h2", "Settings"),
        ("ul", [
            "Go to <b>Settings → Tectora Dakmeting</b> and enter a <b>Google Maps API key</b> (Geocoding + Static Maps) or a <b>Mapbox token</b>. Without a key you can still draw on an uploaded plan.",
            "For Belgian VAT install the Belgian localisation (l10n_be) and use a fiscal position for the 6% renovation rate.",
            "Under <b>Sales → Products → Product Categories</b> check the field <b>Kan gebruikt worden voor</b>: it decides which categories the drawing offers for roof objects, edges, surfaces, corners and seams.",
        ]),
        ("h2", "Menus"),
        ("ul", [
            "<b>Dakmeting</b>: Dakprojecten, Projecten (dashboards), Werkblokken, Dakobjecten, Materiaalbehoefte, Producten, Instellingen.",
            "<b>Sales</b>: every quotation carries a roof project; the smart buttons Dakproject and Projectdashboard sit at the top.",
            "<b>Project</b>: clicking a project opens its dashboard.",
            "<b>Employees → Configuration → Ploegen</b>: the teams; the team itself is set on the employee form.",
        ]),
        ("h2", "Access rights"),
        ("p", "Salespeople (Sales group) can create and edit roof projects; other internal users can read them. Project users see the dashboards, project managers the profitability."),
    ]),
    ("Creating a roof project", [
        ("p", "There are three starting points. All three lead to the same pair of roof project + quotation."),
        ("ul", [
            "<b>From CRM</b>: on an opportunity click <b>Dakproject maken</b>. Customer and address are taken over. A quotation made later on that opportunity links itself to this roof project.",
            "<b>From Sales</b>: create a quotation as usual (with a quotation template if you like). On save a roof project is created automatically with the customer, the delivery address as site address, the salesperson as project manager and the project type from the pricelist.",
            "<b>From Dakmeting</b>: <b>Dakprojecten → New</b>. Pick customer, project type and site address, draw and click <b>Offerte maken</b>.",
        ]),
        ("h2", "Fields on the roof project"),
        ("table", [["Field", "Meaning"],
                   ["Customer, opportunity", "Synchronised with the quotation"],
                   ["Project type", "Renovatie / Nieuwbouw / Industrie; sets the quotation's pricelist"],
                   ["Site address", "Address geocoded for the satellite image"],
                   ["Team, Planned", "Team and period; together they create a work block automatically"],
                   ["Offerte / Order", "The one order of this roof project (history via the smart button)"],
                   ["Project", "The plannable project, created on confirmation"]]),
        ("p", "The status follows the work: Concept → Opgemeten → Offerte gemaakt → Order bevestigd → Afgerond."),
        ("tip", "Save a new roof project before drawing: the sections are created on the server and need the project."),
    ]),
    ("The drawing", [
        ("h2", "Background"),
        ("p", "The globe icon in the toolbar gathers everything about the background: <b>Satellietbeeld ophalen</b> (the site address is geocoded, the scale follows from the map projection), "
              "<b>Eigen plan uploaden</b>, show/hide, transparency and <b>Achtergrond verwijderen</b>."),
        ("h2", "Drawing sections"),
        ("ul", [
            "<b>Rechthoek</b>: drag a rectangle. <b>Polygoon</b>: click the corners and close with a double-click, Enter or a click on the first point.",
            "<b>Selecteer</b>: click to select, drag a selected shape to move it, drag a corner to reshape, double-click to rename, Delete to remove.",
            "<b>Pan</b> and scroll to navigate; <b>F</b> for full screen, <b>Raster</b> for a measuring grid.",
        ]),
        ("h2", "Roof objects"),
        ("p", "Right-click the drawing to add a chimney, dome or other roof object (rectangle or circle). A section can also be converted into a chimney or dome from the Daksecties tab."),
        ("h2", "Seams"),
        ("p", "A <b>seam</b> (naad) marks that two roof surfaces are separate. Pick the <b>Naad</b> tool, click the points and finish with a double-click or Enter. "
              "The seam shows as a dotted line; its label carries the length and opens the product picker with the categories ticked for <b>Naden</b>."),
        ("h2", "Calibrating the scale"),
        ("p", "Right-click a length label and enter the real measured length. The drawing does not move, the scale is recomputed. This is also how you bring an uploaded plan to scale."),
        ("h2", "Edges and upstands"),
        ("p", "In the panel on the right you set an <b>edge width</b> and an <b>upstand height</b> per side (button <b>Overal</b> for all sides). "
              "The inner measurement and the upstand surface are computed and shown as a dotted inner outline."),
        ("h2", "Updating the measurement"),
        ("p", "The measurement is updated automatically on every change. The button <b>Meting bijwerken uit tekening</b> does the same by hand. "
              "Sections and objects are recognised by their canvas id, so assigned products survive."),
    ]),
    ("Assigning products on the drawing", [
        ("p", "Click a label to assign products. Each label type has its own product categories (field <b>Kan gebruikt worden voor</b> on the category):"),
        ("table", [["Label", "Use", "Quantity"],
                   ["Name of the section", "Surface", "Area in m²"],
                   ["Length on a side", "Edges", "Length of that side in m"],
                   ["Corner (white = outer, orange = inner)", "Corners", "1 piece"],
                   ["Name of a roof object", "Roof objects", "Area or 1"],
                   ["Label on a seam", "Seams", "Length of the seam in m"]]),
        ("ul", [
            "<b>Several at once</b>: hold Ctrl and click several sides, surfaces or corners of the same type; release Ctrl and the picker opens once for all of them.",
            "The panel on the right lists the lines of the selected shape with a total; a line is removed with the bin icon.",
            "Quantities follow the measurement: change the shape and the quantities and the quotation change with it.",
        ]),
    ]),
    ("Chapter tabs and quotation lines", [
        ("p", "Below the drawing sit the chapters of the quotation. They mirror the quotation lines that do not come from the drawing."),
        ("ul", [
            "<b>Algemene werken</b> and <b>Veiligheid</b>: a checklist of all products of the chapter; ticking puts the product on the quotation.",
            "<b>Afbraak</b>, <b>Opbouw</b> and <b>Overige</b>: only the products that are on the quotation, with an <b>Add a line</b> offering the products of that chapter only.",
        ]),
        ("p", "The quantity follows the unit of the product: an <b>m²</b> product takes the total roof area, an <b>m</b> product the total perimeter, a counted product (pieces, lump sum, days) the number you enter. "
              "A product the drawing prices itself (on a section or object) disappears from the chapter tabs, so nothing is counted twice."),
        ("tip", "Add a line on the quotation and it appears in the tab of its category. Remove it here and it disappears from the quotation, and vice versa."),
    ]),
    ("Quotation and sales order", [
        ("h2", "One to one"),
        ("p", "Every roof project has one quotation/order and every order one roof project. The smart buttons <b>Offerte / Order</b> (on the roof project) and <b>Dakproject</b> (on the order) are always there; if the counterpart is missing they create it."),
        ("h2", "Creating and refreshing the quotation"),
        ("ul", [
            "<b>Offerte maken</b> on the roof project creates the quotation with a header per roof section and roof object, the chapter lines under their chapter and the pricelist of the project type.",
            "<b>Offerte bijwerken uit meting</b> aligns an open quotation with the measurement; manual lines stay.",
            "A <b>confirmed</b> order is never changed. A <b>cancelled</b> order stays in the history and makes room for a new one.",
        ]),
        ("h2", "Quotation templates"),
        ("p", "Pick a template in Sales (e.g. Renovatie plat dak, PIR 12 cm, EPDM). The template lines become chapter lines on the roof project; the m² and m quantities are replaced at once by the measured area and perimeter."),
        ("h2", "Synchronised fields"),
        ("table", [["Quotation", "Roof project"],
                   ["Customer", "Customer"],
                   ["Opportunity", "Opportunity"],
                   ["Salesperson", "Project manager"],
                   ["Delivery date", "Deadline"],
                   ["Pricelist", "Project type"]]),
        ("p", "What you change on one side appears on the other. Customer and pricelist are only changed on an open quotation."),
        ("note", "The measurement sheet is added automatically as an extra page in the quotation PDF."),
    ]),
    ("Site preparation and printing", [
        ("p", "The <b>Werf</b> tab holds the site sheet: project management and site contact, preparation (Checkin@work, asbestos, height, substrate), access for material and site, transport and waste, "
              "extras (scaffolding, aerial lift, concrete drilling, HVAC, precautions), on-site facilities, roof edges and the EPDM sheets with their total area."),
        ("p", "The yes/no questions are checkboxes: ticked means <b>Ja</b>."),
        ("h2", "Printing"),
        ("ul", [
            "<b>Meetblad dakmeting</b>: the drawing with measurements and the product lines per section.",
            "<b>Projectinformatie werfblad</b>: the completed site sheet for the team.",
        ]),
    ]),
    ("Confirmation: project and dashboard", [
        ("p", "<b>Confirming</b> the order does the following automatically:"),
        ("ul", [
            "A plannable <b>project</b> is created (Odoo Project), named after the customer and the municipality of the site, with its own analytic account. Order and project point at each other.",
            "The <b>material list</b> is built from the bills of materials of the sold products.",
            "The roof project moves to <b>Order bevestigd</b>.",
        ]),
        ("h2", "The dashboard"),
        ("p", "Clicking a project (Project app or Dakmeting → Projecten) opens the dashboard. Every card opens the records behind it:"),
        ("table", [["Card", "Content", "Opens"],
                   ["Omzet", "Order excl. VAT, invoiced / to invoice", "Profitability"],
                   ["Kosten", "All costs on the analytic account (booked / expected)", "Profitability"],
                   ["Marge", "Revenue minus costs, in € and %", "Profitability"],
                   ["Materiaalkost", "Bill of materials × cost price", "Material list"],
                   ["Inkoop", "Purchase orders on the project", "Purchase orders"],
                   ["Urenstaten", "Hours and labour cost", "Timesheets"],
                   ["Facturen", "Count and amount due", "Invoices"],
                   ["Leveringen", "To deliver / partial / delivered", "Deliveries"],
                   ["Taken", "Open and closed tasks", "Tasks"],
                   ["Planning", "Next working day, team, planned hours, employees", "Planning"]]),
        ("p", "The smart buttons <b>Offerte / Order</b> and <b>Dakproject</b> are always available. The <b>Dakmeting</b> tab shows the measurement (drawing, area, perimeter, sections); "
              "the <b>Planning</b>, <b>Taken</b> and <b>Materiaallijst</b> tabs the details. <b>Projectinstellingen</b> opens the standard project form."),
    ]),
    ("Teams and planning", [
        ("h2", "Teams"),
        ("p", "A team (ploeg) is a fixed group of employees with a team leader. The team is set on the <b>employee form</b> (Work tab → Ploeg); the teams themselves are managed under <b>Employees → Configuration → Ploegen</b>. "
              "The Employees app opens per team: drag an employee to another column to change their team."),
        ("h2", "Planning"),
        ("ul", [
            "On the roof project pick a <b>team</b> and the <b>planned start and end</b>. A <b>work block</b> with all team members is created automatically.",
            "<b>Splits per dag</b> turns a multi-day block into one block per day; each block can get its own employees.",
            "With the Planning app every employee becomes a real <b>shift</b>. In the <b>Per ploeg</b> planner you pick a roof project and a team on one shift and the whole team is planned.",
            "The dates of the roof project and the project follow each other; the dashboard shows the next working day and the planned employees.",
        ]),
    ]),
    ("Material list and post-calculation", [
        ("p", "On confirmation every sold product is exploded through its <b>bill of materials</b> (nested kits included) into materials; goods without a bill are the material themselves, a service without one is labour. "
              "Manual lines are kept; lines from an earlier confirmation of the same order are replaced."),
        ("p", "The post-calculation runs on the project's analytic account: customer invoices, vendor bills, purchase orders, stock moves and timesheets come together there. "
              "The dashboard shows revenue, costs and margin; the card opens Odoo's detailed profitability analysis."),
    ]),
    ("Frequently asked questions", [
        ("h2", "The satellite image is not fetched"),
        ("p", "Check the API key in Settings → Tectora Dakmeting and the site address. Without a key you can upload your own plan and calibrate the scale by right-clicking a side length."),
        ("h2", "I cannot assign products"),
        ("p", "The roof project must be saved. If the picker is empty, no product category has the use of that label (surface, edges, corners, roof objects, seams) ticked."),
        ("h2", "The quotation no longer matches the drawing"),
        ("p", "Click <b>Offerte bijwerken uit meting</b>. A confirmed order is not changed: cancel it and make a new quotation, or edit the order itself."),
        ("h2", "No project appears after confirmation"),
        ("p", "Click <b>Projectdashboard</b> on the order: a confirmed order without a project gets one. On an error message, check the server log."),
        ("h2", "An employee is missing from the planning"),
        ("p", "Check that the employee has a team (employee form, Work tab) and a resource (Planning app). The team leader is always included."),
    ]),
]
