/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";

/**
 * Product picker for the roof canvas: the matching products are loaded once
 * and filtered client-side, with one quick-filter button per product
 * category on top.
 *
 * The same products can be assigned to more than one item at once: ticking
 * "toewijzen aan meerdere items" lists every other item of the same type in
 * the drawing (the other sides, the other surfaces, ...) to pick from.
 */
export class RoofProductPickerDialog extends Component {
    static template = "tectora_roof.RoofProductPickerDialog";
    static components = { Dialog };
    props = useProps({
        title: t.string(),
        domain: t.array(),
        onConfirm: t.function(),
        close: t.function(),
        assignedDomain: t.array().optional(),
        assignedLabel: t.string().optional(),
        // Quantity the assignment will get (the clicked side's length, the
        // surface in m², 1 for a corner); shown per row with the subtotal.
        quantity: t.number().optional(),
        // Other items of the same type in the drawing, each
        // {key, label, detail, quantity}. Empty or absent hides the option.
        targets: t.array().optional(),
        // Unit the quantities are in ("m", "m²", ""), for the totals line.
        quantityUnit: t.string().optional(),
        // Target keys ticked from the start: the other sides the user
        // Ctrl-selected on the drawing.
        preselectedTargets: t.array().optional(),
        // How the clicked item is named in the list of what gets the products.
        baseLabel: t.string().optional(),
        // A roof surface: the "Dakopbouw" tab (dampscherm, isolatie,
        // dakbedekking and the EPDM sheets) -- {projectId, preview(targetKeys,
        // margin), apply(choice, targetKeys)}.
        buildup: t.object().optional(),
        // A side of a roof surface: the "Randafwerking" tab (roof edge or
        // connection) -- {projectId, apply(choice, targetKeys, dryRun)}.
        edges: t.object().optional(),
        // A surface or side: the "Afbouw" tab (demolition works to tick) --
        // {projectId, scope ("surface"|"edge"), apply(productIds, optionIds,
        // targetKeys)}.
        demolition: t.object().optional(),
        // A dakobject: the calculator of a chimney ({projectId, objectId,
        // apply(productId, height)}) or of a dome ({projectId, objectId,
        // apply(choice)}).
        chimney: t.object().optional(),
        skylight: t.object().optional(),
        // Tick lists of the drawing's own, each a tab: [{key, label, intro,
        // counted (one piece per item instead of its measure), factorLabel
        // (shows the factor field), load() -> {options, assigned, factors},
        // apply(productIds, optionIds, factors, targetKeys)}].
        selections: t.array().optional(),
    });

    setup() {
        this.orm = useService("orm");
        this.assignedByProduct = {}; // product_id -> [line summaries]
        this.state = proxy({
            products: [],
            tab: "products", // "buildup" (Dakopbouw) or "products"
            activeCategory: null, // false = zonder categorie, null = alle
            search: "",
            selected: {},
            // Free products on top of a calculator tab: [{id, mode
            // ("measure" | "fixed"), factor, quantity, conditional}].
            extras: [],
            extraSearch: "",
            // A Ctrl-selection arrives with its extra targets already picked,
            // so the list of what gets the products is open and complete.
            multi: (this.props.preselectedTargets || []).length > 0,
            selectedTargets: Object.fromEntries(
                (this.props.preselectedTargets || []).map((key) => [key, true])
            ),
        });
        // The build-up tab: per layer the chosen type, thickness and product.
        this.buildup = proxy({
            loaded: false,
            options: { vapour: [], insulation: [], membrane: [] },
            vapour: 0,
            insulation: { type: "", thickness: "", product: 0 },
            membrane: { type: "", thickness: "", product: 0 },
            sheets: true,
            margin: 0.1, // along a rand, on top of upstand and edge width
            seamOverlap: 0.15, // along a seam
            maxWidth: 15.25,
            preview: [],
            previewLoading: false,
            vapourPreview: null, // the vapour barrier's quantity and its figures
            kimfixProduct: null, // the kimfixatie product of the catalogue
            kimfix: true, // the kimfixatie on every side and around the objects
            details: true, // the calculation under every sheet
        });
        // The edge tab: a roof edge (type, height, finish) or a connection.
        this.edges = proxy({
            loaded: false,
            options: { edges: [], connections: [] },
            kind: "edge", // "edge" (dakrand) or "connection" (aansluiting)
            edge: { type: "", height: "", product: 0 },
            connections: {}, // product id -> true: a side takes several
            corners: true,
            preview: null,
            previewLoading: false,
            // Width (dakrand) and upstand (opstand) of the sides, in m; set on
            // every chosen side once changed here.
            width: (this.props.edges && this.props.edges.width) || 0,
            upstand: (this.props.edges && this.props.edges.upstand) || 0,
            widthChanged: false,
            upstandChanged: false,
        });
        // The demolition tab: the works to tick, grouped.
        this.demolition = proxy({ loaded: false, options: [], selected: {} });
        if (this.props.buildup) {
            this.state.tab = "buildup";
        } else if (this.props.edges) {
            this.state.tab = "edges";
        } else if (this.props.demolition) {
            this.state.tab = "demolition";
        }
        this.chimney = proxy({ loaded: false, data: null, mode: "uitbekleden", product: 0, height: 0 });
        this.skylight = proxy({
            loaded: false, data: null, mode: "set", size: "", dome: "", curb: "", rwa: "",
            extras: {}, // product id -> quantity, for the ticked ones
        });
        if (this.props.chimney) {
            this.state.tab = "chimney";
        } else if (this.props.skylight) {
            this.state.tab = "skylight";
        }
        // The drawing's tick lists; one that is the item's main tab (a
        // tapbuis has nothing else) opens first.
        this.selections = proxy({});
        for (const definition of this.props.selections || []) {
            this.selections[definition.key] = { loaded: false, options: [], selected: {}, factors: {} };
            if (definition.main && this.state.tab === "products") {
                this.state.tab = `sel:${definition.key}`;
            }
        }
        onWillStart(async () => {
            if (this.props.buildup) {
                await this.loadBuildup();
            }
            if (this.props.edges) {
                await this.loadEdges();
            }
            this.state.products = await this.orm.searchRead(
                "product.product",
                this.props.domain,
                ["default_code", "name", "list_price", "uom_id", "categ_id"],
                { limit: 1000, order: "default_code, name" }
            );
            if (this.props.assignedDomain) {
                const lines = await this.orm.searchRead(
                    "tectora.roof.section.product",
                    this.props.assignedDomain,
                    ["product_id", "coverage", "side_display", "quantity", "uom_id"]
                );
                for (const line of lines) {
                    const productId = line.product_id[0];
                    (this.assignedByProduct[productId] ||= []).push(
                        this.lineSummary(line)
                    );
                }
            }
            if (this.props.demolition) {
                await this.loadDemolition();
            }
            if (this.props.chimney) {
                await this.loadChimney();
            }
            if (this.props.skylight) {
                await this.loadSkylight();
            }
            await this.loadSelections();
        });
    }

    // ------------------------------------------------------ free products
    // Every calculator tab takes extra products of free choice along: they
    // are assigned to the same item(s) when the tab is applied, next to what
    // the calculator itself puts there. Each either follows the item's
    // measure times a factor (8 per m², 0.12 for 12 %) or is a fixed number
    // (a forfait), and can be a conditional item (worst case: on the
    // quotation with its price and a quantity of 0).

    get hasExtras() {
        return this.state.extras.length > 0;
    }

    /** Whether a unit is counted in pieces (rounded up when it follows a
     * measure). */
    isCounted(uom) {
        return !["m²", "m2", "m", "lm", "m³", "m3"].includes(String(uom || "").trim().toLowerCase());
    }

    /** A quantity as shown: whole numbers as they are, others with two
     * decimals. (A method, not in the template: only a few globals, such as
     * Math, are known there -- Number is not.) */
    formatQuantity(value) {
        const number = Number(value) || 0;
        return Number.isInteger(number) ? String(number) : number.toFixed(2);
    }

    get extraLines() {
        const lines = [];
        for (const extra of this.state.extras) {
            const product = this.state.products.find((p) => p.id === extra.id);
            if (!product) {
                continue;
            }
            const uom = product.uom_id ? product.uom_id[1] : "";
            let total;
            if (extra.mode === "fixed") {
                total = (extra.quantity || 0) * this.itemCount;
            } else {
                total = this.totalQuantity * (extra.factor || 1);
                if ((extra.factor || 1) !== 1 && this.isCounted(uom)) {
                    total = Math.ceil(total - 1e-9);
                }
            }
            lines.push({
                id: extra.id,
                product,
                extra,
                uom,
                total,
                subtotal: extra.conditional ? 0 : product.list_price * total,
            });
        }
        return lines;
    }

    get extrasTotal() {
        return this.extraLines.reduce((sum, line) => sum + line.subtotal, 0);
    }

    /** The products the search finds, without those already added. */
    get extraMatches() {
        const query = this.state.extraSearch.trim().toLowerCase();
        if (!query) {
            return [];
        }
        const taken = new Set(this.state.extras.map((extra) => extra.id));
        const matches = [];
        for (const product of this.state.products) {
            if (taken.has(product.id)) {
                continue;
            }
            if (
                product.name.toLowerCase().includes(query) ||
                (product.default_code || "").toLowerCase().includes(query)
            ) {
                matches.push(product);
                if (matches.length >= 12) {
                    break;
                }
            }
        }
        return matches;
    }

    addExtra(product) {
        if (!this.state.extras.some((extra) => extra.id === product.id)) {
            this.state.extras.push({
                id: product.id, mode: "measure", factor: 1, quantity: 1, conditional: false,
            });
        }
        this.state.extraSearch = "";
    }

    removeExtra(productId) {
        this.state.extras = this.state.extras.filter((extra) => extra.id !== productId);
    }

    setExtra(productId, field, value) {
        const extra = this.state.extras.find((e) => e.id === productId);
        if (!extra) {
            return;
        }
        if (field === "factor" || field === "quantity") {
            const number = parseFloat(String(value).replace(",", "."));
            extra[field] = number >= 0 ? number : field === "factor" ? 1 : 0;
        } else {
            extra[field] = value;
        }
    }

    /** What applyExtras needs, taken before the dialog closes. */
    takeExtras() {
        const ids = this.state.extras.map((extra) => extra.id);
        const options = {};
        for (const extra of this.state.extras) {
            options[extra.id] = {
                mode: extra.mode,
                factor: extra.factor || 1,
                quantity: extra.quantity || 0,
                conditional: Boolean(extra.conditional),
            };
        }
        return { ids, options };
    }

    async applyExtras(extras, targetKeys) {
        if (extras.ids.length) {
            await this.props.onConfirm(extras.ids, targetKeys || [], extras.options);
        }
    }

    // ---------------------------------------------------------- tick lists
    // Tabs given by the drawing (``props.selections``): a list of products to
    // tick for the item, each with how many go per unit of its measure --
    // the terrace floor of a surface (supports per m², tiles, cutting
    // waste), the works on a tapbuis (one piece each).

    async loadSelections() {
        for (const definition of this.props.selections || []) {
            const data = await definition.load();
            const options = data.options || [];
            const assigned = new Set(data.assigned || []);
            const factors = data.factors || {};
            this.selections[definition.key] = {
                loaded: true,
                options,
                selected: Object.fromEntries(
                    options.filter((p) => assigned.has(p.id)).map((p) => [p.id, true])
                ),
                factors: Object.fromEntries(
                    options.map((p) => [p.id, factors[p.id] || p.factor || 1])
                ),
            };
        }
    }

    get activeSelection() {
        return (this.props.selections || []).find((d) => `sel:${d.key}` === this.state.tab) || null;
    }

    selectionGroups(key) {
        const groups = [];
        for (const product of this.selections[key].options) {
            let group = groups.find((g) => g.label === product.group);
            if (!group) {
                group = { label: product.group, products: [] };
                groups.push(group);
            }
            group.products.push(product);
        }
        return groups;
    }

    toggleSelection(key, product) {
        const selected = this.selections[key].selected;
        if (selected[product.id]) {
            delete selected[product.id];
        } else {
            selected[product.id] = true;
        }
    }

    setSelectionFactor(key, product, value) {
        const number = parseFloat(String(value).replace(",", "."));
        this.selections[key].factors[product.id] = number > 0 ? number : 1;
    }

    selectionLines(definition) {
        const state = this.selections[definition.key];
        // A counted item (a tapbuis) is one piece each; a measured one its
        // m² or m.
        const measure = definition.counted ? this.itemCount : this.totalQuantity;
        return state.options.filter((p) => state.selected[p.id]).map((product) => {
            const factor = state.factors[product.id] || 1;
            let quantity = measure * factor;
            if (this.isCounted(product.uom)) {
                quantity = Math.ceil(quantity - 1e-9);
            }
            return { product, factor, quantity, subtotal: product.price * quantity };
        });
    }

    selectionTotal(definition) {
        return this.selectionLines(definition).reduce((sum, line) => sum + line.subtotal, 0);
    }

    async applySelectionTab() {
        const definition = this.activeSelection;
        if (!definition) {
            return;
        }
        const state = this.selections[definition.key];
        const optionIds = state.options.map((p) => p.id);
        const productIds = optionIds.filter((id) => state.selected[id]);
        const factors = Object.fromEntries(productIds.map((id) => [id, state.factors[id] || 1]));
        const targetKeys = this.selectedTargetKeys;
        const extras = this.takeExtras();
        this.props.close();
        if (optionIds.length) {
            await definition.apply(productIds, optionIds, factors, targetKeys);
        }
        await this.applyExtras(extras, targetKeys);
    }

    // ------------------------------------------------------------ build-up
    async loadBuildup() {
        const data = await this.orm.call(
            "tectora.roof.project", "tectora_get_buildup_options", [[this.props.buildup.projectId]]
        );
        const b = this.buildup;
        b.options = data.options;
        b.margin = data.margin;
        b.kimfixProduct = data.kimfix || null;
        b.seamOverlap = data.seam_overlap;
        b.maxWidth = data.max_width;
        b.vapour = data.current.vapour || 0;
        for (const layer of ["insulation", "membrane"]) {
            const product = b.options[layer].find((p) => p.id === data.current[layer]);
            b[layer] = product
                ? { type: product.type, thickness: product.thickness_label, product: product.id }
                : { type: "", thickness: "", product: 0 };
        }
        b.loaded = true;
        this.refreshSheets();
        this.refreshVapour();
        this.refreshEdgeCorners();
    }

    setTab(tab) {
        this.state.tab = tab;
    }

    layerTypes(layer) {
        return [...new Set(this.buildup.options[layer].map((p) => p.type))];
    }

    layerThicknesses(layer) {
        const choice = this.buildup[layer];
        const seen = new Map();
        for (const product of this.buildup.options[layer]) {
            if (product.type === choice.type && !seen.has(product.thickness_label)) {
                seen.set(product.thickness_label, product.thickness);
            }
        }
        return [...seen.entries()]
            .sort((a, b) => a[1] - b[1])
            .map(([label]) => label);
    }

    layerProducts(layer) {
        const choice = this.buildup[layer];
        return this.buildup.options[layer].filter(
            (p) => p.type === choice.type && p.thickness_label === choice.thickness
        );
    }

    productLabel(product) {
        const parts = [product.variant, product.fixing].filter(Boolean);
        const label = parts.length ? parts.join(" · ") : product.name;
        return `${label} — € ${product.price.toFixed(2)}/${product.uom}`;
    }

    vapourLabel(product) {
        const head = product.variant ? `${product.variant} · ` : "";
        return `${head}${product.type} — € ${product.price.toFixed(2)}/${product.uom}`;
    }

    setVapour(value) {
        this.buildup.vapour = parseInt(value) || 0;
    }

    /** The vapour barrier's quantity: inner surface less the objects, plus
     * up the upstands and around the objects the insulation + 5 cm. */
    async refreshVapour() {
        const b = this.buildup;
        if (!this.props.buildup || !this.props.buildup.previewVapour) {
            return;
        }
        const ticket = (this._vapourTicket = (this._vapourTicket || 0) + 1);
        const result = await this.props.buildup.previewVapour(
            this.selectedTargetKeys, b.insulation.product || false
        );
        if (ticket === this._vapourTicket) {
            b.vapourPreview = result;
        }
    }

    kimfixFigures(row) {
        const n = (v) => v.toFixed(2);
        const objects = row.kimfix_objects ? ` + ${n(row.kimfix_objects)} m rond schoorstenen en koepels` : "";
        return `${row.name}: ${n(row.sides)} m randen${objects} = ${n(row.kimfix)} m`;
    }

    figuresFor(line, row) {
        if (line.layer === "vapour") {
            return this.vapourFigures(row);
        }
        if (line.layer === "kimfix") {
            return this.kimfixFigures(row);
        }
        if (line.layer === "membrane") {
            const n = (v) => v.toFixed(2);
            return `${row.name}: ${n(row.area)} m² vlak + ${n(row.upstand_area)} m² opstanden = ${n(row.membrane)} m²`;
        }
        return this.insulationFigures(row);
    }

    toggleKimfix(checked) {
        this.buildup.kimfix = checked;
    }

    insulationFigures(row) {
        const n = (v) => v.toFixed(2);
        const objects = row.object_area ? ` − ${n(row.object_area)} m² objecten` : "";
        return `${row.name}: ${n(row.surface)} m² binnenopp.${objects} = ${n(row.insulation)} m²`;
    }

    vapourFigures(row) {
        const n = (v) => v.toFixed(2);
        let text = `${row.name}: ${n(row.surface)} m² binnenopp.`;
        if (row.object_area) {
            text += ` − ${n(row.object_area)} m² objecten`;
        }
        const up = row.upstand_length + row.object_perimeter;
        if (up) {
            const parts = [];
            if (row.upstand_length) {
                parts.push(`${n(row.upstand_length)} m opstand`);
            }
            if (row.object_perimeter) {
                parts.push(`${n(row.object_perimeter)} m rond objecten`);
            }
            text += ` + (${parts.join(" + ")}) × (${Math.round(row.thickness * 100)} cm isolatie + 5 cm)`;
        }
        return `${text} = ${n(row.quantity)} m²`;
    }

    /** After a type or thickness change: the first product that fits. */
    pickLayer(layer, field, value) {
        const choice = this.buildup[layer];
        choice[field] = value;
        if (field === "type") {
            const thicknesses = this.layerThicknesses(layer);
            if (!thicknesses.includes(choice.thickness)) {
                choice.thickness = thicknesses[0] || "";
            }
        }
        if (field !== "product") {
            const products = this.layerProducts(layer);
            if (!products.some((p) => p.id === choice.product)) {
                choice.product = products.length ? products[0].id : 0;
            }
        } else {
            choice.product = parseInt(value) || 0;
        }
        if (!choice.type) {
            choice.thickness = "";
            choice.product = 0;
        }
        if (layer === "insulation") {
            this.refreshVapour();
        }
    }

    get buildupChoice() {
        const b = this.buildup;
        return {
            vapour_id: parseInt(b.vapour) || false,
            insulation_id: b.insulation.product || false,
            membrane_id: b.membrane.product || false,
        };
    }

    get buildupLines() {
        const b = this.buildup;
        const choice = this.buildupChoice;
        const lines = [];
        const add = (layer, label, id) => {
            const product = id && b.options[layer].find((p) => p.id === id);
            if (product) {
                // The vapour barrier and the insulation have their own
                // measure (inner surface, objects).
                const preview = b.vapourPreview;
                let quantity = this.totalQuantity;
                if (preview && layer === "vapour") {
                    quantity = preview.quantity;
                } else if (preview && layer === "insulation") {
                    quantity = preview.insulation_quantity;
                } else if (preview && layer === "membrane" && preview.membrane_quantity !== undefined) {
                    // The roof covering runs up the upstands.
                    quantity = preview.membrane_quantity;
                }
                lines.push({
                    label,
                    product,
                    quantity,
                    layer,
                    figures: preview
                        ? preview.sections.filter((row) => layer !== "membrane" || row.upstand_area)
                        : [],
                    subtotal: product.price * quantity,
                });
            }
        };
        add("vapour", "Dampscherm", choice.vapour_id);
        add("insulation", "Isolatie", choice.insulation_id);
        add("membrane", "Dakbedekking", choice.membrane_id);
        if (b.kimfix && b.kimfixProduct && b.vapourPreview) {
            const quantity = b.vapourPreview.kimfix_quantity;
            lines.push({
                label: "Kimfixatie",
                product: b.kimfixProduct,
                quantity,
                layer: "kimfix",
                figures: b.vapourPreview.sections,
                subtotal: b.kimfixProduct.price * quantity,
            });
        }
        return lines;
    }

    get buildupTotal() {
        return this.buildupLines.reduce((sum, line) => sum + line.subtotal, 0);
    }

    get canApplyBuildup() {
        const choice = this.buildupChoice;
        return Boolean(
            choice.vapour_id || choice.insulation_id || choice.membrane_id || this.buildup.sheets
            || this.hasExtras
        );
    }

    get sheetsTotal() {
        return this.buildup.preview.reduce((sum, sheet) => sum + sheet.area, 0);
    }

    /** ``field`` "margin" (rand) or "seamOverlap" (naad), typed in cm. */
    onMarginInput(ev, field = "margin") {
        const value = parseFloat(String(ev.target.value).replace(",", "."));
        this.buildup[field] = value >= 0 ? value / 100 : 0;
        this.refreshSheets();
        this.refreshEdgeCorners();
        this.refreshVapour();
    }

    toggleSheetDetails(checked) {
        this.buildup.details = checked;
    }

    toggleSheets(checked) {
        this.buildup.sheets = checked;
        this.refreshSheets();
        this.refreshEdgeCorners();
        this.refreshVapour();
    }

    async refreshSheets() {
        const b = this.buildup;
        if (!this.props.buildup || !b.sheets) {
            b.preview = [];
            return;
        }
        const ticket = (this._sheetTicket = (this._sheetTicket || 0) + 1);
        b.previewLoading = true;
        try {
            const preview = await this.props.buildup.preview(this.selectedTargetKeys, {
                margin: b.margin,
                seam_overlap: b.seamOverlap,
            });
            if (ticket === this._sheetTicket) {
                b.preview = preview || [];
            }
        } finally {
            if (ticket === this._sheetTicket) {
                b.previewLoading = false;
            }
        }
    }

    allSurfaces() {
        this.state.multi = true;
        this.selectAllTargets(true);
    }

    async applyBuildup() {
        if (!this.canApplyBuildup) {
            return;
        }
        const targetKeys = this.selectedTargetKeys;
        const choice = {
            ...this.buildupChoice,
            sheets: this.buildup.sheets,
            kimfix: this.buildup.kimfixProduct ? this.buildup.kimfix : null,
            margin: this.buildup.margin,
            seam_overlap: this.buildup.seamOverlap,
        };
        const extras = this.takeExtras();
        this.props.close();
        await this.props.buildup.apply(choice, targetKeys);
        await this.applyExtras(extras, targetKeys);
    }

    // ------------------------------------------------------- edge finish
    async loadEdges() {
        const data = await this.orm.call(
            "tectora.roof.project", "tectora_get_edge_options", [[this.props.edges.projectId]]
        );
        this.edges.options = data;
        this.edges.loaded = true;
    }

    get edgeTypes() {
        return [...new Set(this.edges.options.edges.map((p) => p.type))];
    }

    get edgeHeights() {
        const choice = this.edges.edge;
        const seen = new Map();
        for (const product of this.edges.options.edges) {
            if (product.type === choice.type && !seen.has(product.height_label)) {
                seen.set(product.height_label, product.height);
            }
        }
        return [...seen.entries()].sort((a, b) => a[1] - b[1]).map(([label]) => label);
    }

    get edgeHasHeights() {
        return this.edgeHeights.some((height) => height);
    }

    get edgeFinishes() {
        const choice = this.edges.edge;
        return this.edges.options.edges.filter(
            (p) => p.type === choice.type && p.height_label === choice.height
        );
    }

    edgeFinishLabel(product) {
        return `${product.finish || product.name} — € ${product.price.toFixed(2)}/${product.uom}`;
    }

    get connectionGroups() {
        const groups = [];
        for (const product of this.edges.options.connections) {
            let group = groups.find((g) => g.label === product.group);
            if (!group) {
                group = { label: product.group, products: [] };
                groups.push(group);
            }
            group.products.push(product);
        }
        return groups;
    }

    setEdgeKind(kind) {
        this.edges.kind = kind;
        this.refreshEdgeCorners();
    }

    pickEdge(field, value) {
        const choice = this.edges.edge;
        if (field === "product") {
            choice.product = parseInt(value) || 0;
        } else {
            choice[field] = value;
            if (field === "type") {
                const heights = this.edgeHeights;
                if (!heights.includes(choice.height)) {
                    choice.height = heights[0] || "";
                }
            }
            const finishes = this.edgeFinishes;
            if (!finishes.some((p) => p.id === choice.product)) {
                choice.product = finishes.length ? finishes[0].id : 0;
            }
        }
        if (!choice.type) {
            choice.height = "";
            choice.product = 0;
        }
        this.refreshEdgeCorners();
    }

    toggleConnection(product) {
        const chosen = this.edges.connections;
        if (chosen[product.id]) {
            delete chosen[product.id];
        } else {
            chosen[product.id] = true;
        }
    }

    get connectionIds() {
        return this.edges.options.connections
            .filter((p) => this.edges.connections[p.id])
            .map((p) => p.id);
    }

    toggleEdgeCorners(checked) {
        this.edges.corners = checked;
        this.refreshEdgeCorners();
    }

    /** The roof edge chosen, or (a connection) the first one ticked. */
    get edgeProductId() {
        return this.edges.kind === "edge" ? this.edges.edge.product : this.connectionIds[0] || 0;
    }

    get edgeProduct() {
        const id = this.edgeProductId;
        const list = this.edges.kind === "edge" ? this.edges.options.edges : this.edges.options.connections;
        return list.find((p) => p.id === id) || null;
    }

    get edgeChoice() {
        const e = this.edges;
        const geometry = e.widthChanged || e.upstandChanged
            ? {
                  width: e.widthChanged ? e.width : null,
                  upstand: e.upstandChanged ? e.upstand : null,
              }
            : null;
        // A side takes one roof edge, or one or more connections.
        const connections = this.connectionIds;
        const productId = e.kind === "edge"
            ? this.edgeProductId
            : connections.length ? connections : 0;
        return { kind: e.kind, product_id: productId, corners: e.corners, geometry };
    }

    /** Typed in cm, kept in m. */
    setSideValue(field, ev) {
        const value = parseFloat(String(ev.target.value).replace(",", ".")) / 100;
        this.edges[field] = value > 0 ? Math.round(value * 1000) / 1000 : 0;
        this.edges[`${field}Changed`] = true;
        ev.target.value = this.toCm(this.edges[field]);
    }

    toCm(meters) {
        return Math.round((meters || 0) * 1000) / 10;
    }

    get hasEdgeChoice() {
        return Boolean(this.edgeProductId || this.edges.widthChanged || this.edges.upstandChanged);
    }

    get canApplyEdges() {
        return this.hasEdgeChoice || this.hasExtras;
    }

    /** The corner pieces the roof edge brings (dry run on the server). */
    async refreshEdgeCorners() {
        const e = this.edges;
        if (!this.props.edges || e.kind !== "edge" || !e.corners || !this.edgeProductId) {
            e.preview = null;
            return;
        }
        const ticket = (this._edgeTicket = (this._edgeTicket || 0) + 1);
        e.previewLoading = true;
        try {
            const preview = await this.props.edges.apply(this.edgeChoice, this.selectedTargetKeys, true);
            if (ticket === this._edgeTicket) {
                e.preview = preview;
            }
        } finally {
            if (ticket === this._edgeTicket) {
                e.previewLoading = false;
            }
        }
    }

    get edgeLines() {
        if (this.edges.kind === "connection") {
            return this.edges.options.connections
                .filter((p) => this.edges.connections[p.id])
                .map((p) => ({
                    key: `c${p.id}`,
                    measured: true,
                    name: p.name,
                    quantity: this.totalQuantity,
                    uom: p.uom,
                    subtotal: p.price * this.totalQuantity,
                }));
        }
        const product = this.edgeProduct;
        if (!product) {
            return [];
        }
        const lines = [{
            key: "side",
            measured: true,
            name: product.name,
            quantity: this.totalQuantity,
            uom: product.uom,
            subtotal: product.price * this.totalQuantity,
        }];
        const preview = this.edges.kind === "edge" && this.edges.corners ? this.edges.preview : null;
        if (preview) {
            for (const kind of ["inner", "outer"]) {
                const count = preview.corners[kind];
                if (count) {
                    lines.push({
                        key: kind,
                        name: preview[`${kind}_product`],
                        quantity: count,
                        uom: "st",
                        subtotal: count * preview[`${kind}_price`],
                    });
                }
            }
        }
        return lines;
    }

    get edgeTotal() {
        return this.edgeLines.reduce((sum, line) => sum + line.subtotal, 0);
    }

    async applyEdges() {
        if (!this.canApplyEdges) {
            return;
        }
        const targetKeys = this.selectedTargetKeys;
        const choice = this.edgeChoice;
        const withEdge = this.hasEdgeChoice;
        const extras = this.takeExtras();
        this.props.close();
        if (withEdge) {
            await this.props.edges.apply(choice, targetKeys, false);
        }
        await this.applyExtras(extras, targetKeys);
    }

    // ------------------------------------------------------------- chimney
    async loadChimney() {
        const c = this.chimney;
        c.data = await this.orm.call(
            "tectora.roof.project", "tectora_get_chimney_options",
            [[this.props.chimney.projectId], this.props.chimney.objectId]
        );
        c.height = c.data.measures.height || 1;
        const current = c.data.products.find((p) => p.id === c.data.current);
        if (current) {
            c.mode = current.mode;
            c.product = current.id;
        } else {
            const first = c.data.products.find((p) => p.mode === c.mode);
            c.product = first ? first.id : 0;
        }
        c.loaded = true;
    }

    get chimneyProducts() {
        return this.chimney.data.products.filter((p) => p.mode === this.chimney.mode);
    }

    setChimneyMode(mode) {
        const c = this.chimney;
        c.mode = mode;
        const current = c.data.products.find((p) => p.id === c.product);
        const same = current && this.chimneyProducts.find((p) => p.material === current.material);
        c.product = same ? same.id : (this.chimneyProducts[0] || {}).id || 0;
    }

    setChimneyProduct(value) {
        this.chimney.product = parseInt(value) || 0;
    }

    setChimneyHeight(ev) {
        const value = parseFloat(String(ev.target.value).replace(",", "."));
        this.chimney.height = value >= 0 ? value : 0;
    }

    /** The m² of the cladding: the sides, and the top when wrapped. */
    get chimneyFigures() {
        const c = this.chimney;
        const m = c.data.measures;
        const sides = m.perimeter * c.height;
        const top = c.mode === "inpakken" ? m.area : 0;
        const product = c.data.products.find((p) => p.id === c.product);
        const quantity = Math.round((sides + top) * 100) / 100;
        return { sides, top, quantity, product, subtotal: product ? product.price * quantity : 0 };
    }

    async applyChimney() {
        const c = this.chimney;
        const extras = this.takeExtras();
        this.props.close();
        if (c.product) {
            await this.props.chimney.apply(c.product, c.height);
        }
        await this.applyExtras(extras, []);
    }

    // ------------------------------------------------------------- skylight
    async loadSkylight() {
        const k = this.skylight;
        const data = await this.orm.call(
            "tectora.roof.project", "tectora_get_skylight_options",
            [[this.props.skylight.projectId], this.props.skylight.objectId]
        );
        k.data = data;
        const current = data.current;
        k.mode = current.mode;
        k.size = current.size;
        k.dome = current.dome || data.options.dome[0];
        k.curb = current.curb || data.options.curb[0];
        k.rwa = current.rwa || data.options.rwa[0];
        k.extras = Object.fromEntries(
            data.extras.filter((e) => current.extras.includes(e.id)).map((e) => [e.id, e.quantity])
        );
        k.loaded = true;
    }

    skylightPrice(line, option) {
        const k = this.skylight;
        const row = (((k.data.prices || {})[line] || {})[option] || {})[k.size];
        return row && row.price ? row.price : 0;
    }

    get skylightLines() {
        const k = this.skylight;
        const lines = [];
        const add = (line, option) => {
            const price = this.skylightPrice(line, option);
            lines.push({
                key: line, label: `${k.data.labels[line]} — ${option} — ${k.size}`, quantity: 1,
                uom: "st", price, subtotal: price, missing: !price,
            });
        };
        if (k.mode === "rwa") {
            add("rwa", k.rwa);
        } else {
            add("dome", k.dome);
            add("curb", k.curb);
        }
        for (const extra of k.data.extras) {
            const quantity = k.extras[extra.id];
            if (quantity !== undefined) {
                lines.push({
                    key: `x${extra.id}`, label: extra.name, quantity, uom: extra.uom,
                    price: extra.price, subtotal: extra.price * quantity, missing: false,
                });
            }
        }
        return lines;
    }

    get skylightTotal() {
        return this.skylightLines.reduce((sum, line) => sum + line.subtotal, 0);
    }

    toggleSkylightExtra(extra) {
        const k = this.skylight;
        if (k.extras[extra.id] !== undefined) {
            delete k.extras[extra.id];
        } else {
            k.extras[extra.id] = extra.quantity;
        }
    }

    setSkylight(field, value) {
        this.skylight[field] = value;
    }

    async applySkylight() {
        const k = this.skylight;
        const choice = {
            mode: k.mode, size: k.size, dome: k.dome, curb: k.curb, rwa: k.rwa,
            extras: Object.entries(k.extras).map(([id, quantity]) => ({ id: parseInt(id), quantity })),
        };
        const extras = this.takeExtras();
        this.props.close();
        await this.props.skylight.apply(choice);
        await this.applyExtras(extras, []);
    }

    // ------------------------------------------------------------ demolition
    async loadDemolition() {
        const options = await this.orm.call(
            "tectora.roof.project", "tectora_get_demolition_options",
            [[this.props.demolition.projectId], this.props.demolition.scope]
        );
        this.demolition.options = options;
        // What the clicked surface or side has already is ticked.
        this.demolition.selected = Object.fromEntries(
            options.filter((p) => this.assignedByProduct[p.id]).map((p) => [p.id, true])
        );
        this.demolition.loaded = true;
    }

    get demolitionGroups() {
        const groups = [];
        for (const product of this.demolition.options) {
            let group = groups.find((g) => g.label === product.group);
            if (!group) {
                group = { label: product.group, products: [] };
                groups.push(group);
            }
            group.products.push(product);
        }
        return groups;
    }

    toggleDemolition(product) {
        if (this.demolition.selected[product.id]) {
            delete this.demolition.selected[product.id];
        } else {
            this.demolition.selected[product.id] = true;
        }
    }

    get demolitionSelected() {
        return this.demolition.options.filter((p) => this.demolition.selected[p.id]);
    }

    get demolitionTotal() {
        return this.demolitionSelected.reduce((sum, p) => sum + p.price * this.totalQuantity, 0);
    }

    async applyDemolition() {
        const productIds = this.demolitionSelected.map((p) => p.id);
        const optionIds = this.demolition.options.map((p) => p.id);
        const targetKeys = this.selectedTargetKeys;
        const extras = this.takeExtras();
        this.props.close();
        if (optionIds.length) {
            await this.props.demolition.apply(productIds, optionIds, targetKeys);
        }
        await this.applyExtras(extras, targetKeys);
    }

    lineSummary(line) {
        const labels = {
            surface: "Oppervlak",
            edges: "Randen",
            corners: "Hoeken",
            drainage: "Afvoer",
            general: "Algemeen",
        };
        const parts = [labels[line.coverage] || line.coverage];
        if (line.side_display) {
            parts.push(line.side_display);
        }
        const uom = line.uom_id ? ` ${line.uom_id[1]}` : "";
        return `${parts.join(" · ")} — ${line.quantity.toFixed(2)}${uom}`;
    }

    get categories() {
        const byId = new Map();
        for (const product of this.state.products) {
            if (!product.categ_id) {
                continue;
            }
            const [id, fullName] = product.categ_id;
            const entry = byId.get(id) || {
                id,
                label: String(fullName).split(" / ").pop(),
                count: 0,
            };
            entry.count++;
            byId.set(id, entry);
        }
        return [...byId.values()].sort((a, b) => a.label.localeCompare(b.label));
    }

    get visibleProducts() {
        const query = this.state.search.trim().toLowerCase();
        const category = this.state.activeCategory;
        return this.state.products.filter((product) => {
            if (category !== null && (!product.categ_id || product.categ_id[0] !== category)) {
                return false;
            }
            if (!query) {
                return true;
            }
            return (
                product.name.toLowerCase().includes(query) ||
                (product.default_code || "").toLowerCase().includes(query)
            );
        });
    }

    // Visible products as rows, with the products already assigned to the
    // clicked shape pinned on top under their own header.
    get visibleRows() {
        const products = this.visibleProducts;
        const assigned = products.filter((p) => this.assignedByProduct[p.id]);
        const rest = products.filter((p) => !this.assignedByProduct[p.id]);
        const rows = [];
        if (assigned.length) {
            rows.push({
                key: "header-assigned",
                header: this.props.assignedLabel || "Reeds toegewezen aan dit onderdeel",
            });
            rows.push(...assigned.map((p) => ({ key: `p${p.id}`, product: p, assigned: true })));
            if (rest.length) {
                rows.push({ key: "header-rest", header: "Overige producten" });
            }
        }
        rows.push(...rest.map((p) => ({ key: `p${p.id}`, product: p, assigned: false })));
        return rows;
    }

    get selectedIds() {
        return Object.keys(this.state.selected).map(Number);
    }

    // ------------------------------------------------------- multiple items
    get targets() {
        return this.props.targets || [];
    }

    get selectedTargetKeys() {
        if (!this.state.multi) {
            return [];
        }
        return this.targets
            .filter((target) => this.state.selectedTargets[target.key])
            .map((target) => target.key);
    }

    // The clicked item plus every extra item ticked: what one product row
    // actually adds up to.
    get totalQuantity() {
        const base = this.props.quantity || 0;
        const keys = new Set(this.selectedTargetKeys);
        return this.targets.reduce(
            (total, target) => total + (keys.has(target.key) ? target.quantity : 0),
            base
        );
    }

    get itemCount() {
        return 1 + this.selectedTargetKeys.length;
    }

    toggleMulti(checked) {
        this.state.multi = checked;
        if (!checked) {
            this.state.selectedTargets = {};
        }
        this.refreshSheets();
        this.refreshEdgeCorners();
        this.refreshVapour();
    }

    get baseLabel() {
        return this.props.baseLabel || "Het aangeklikte item";
    }

    toggleTarget(target) {
        if (this.state.selectedTargets[target.key]) {
            delete this.state.selectedTargets[target.key];
        } else {
            this.state.selectedTargets[target.key] = true;
        }
        this.refreshSheets();
        this.refreshEdgeCorners();
        this.refreshVapour();
    }

    selectAllTargets(select) {
        this.state.selectedTargets = select
            ? Object.fromEntries(this.targets.map((target) => [target.key, true]))
            : {};
        this.refreshSheets();
        this.refreshEdgeCorners();
        this.refreshVapour();
    }

    setCategory(categoryId) {
        this.state.activeCategory = categoryId;
    }

    toggle(product) {
        if (this.state.selected[product.id]) {
            delete this.state.selected[product.id];
        } else {
            this.state.selected[product.id] = true;
        }
    }

    async confirm() {
        const ids = this.selectedIds;
        const targetKeys = this.selectedTargetKeys;
        this.props.close();
        if (ids.length) {
            await this.props.onConfirm(ids, targetKeys);
        }
    }
}
