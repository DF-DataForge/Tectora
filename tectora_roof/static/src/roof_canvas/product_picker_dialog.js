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
            margin: 0.1,
            maxWidth: 15.25,
            preview: [],
            previewLoading: false,
            details: true, // the calculation under every sheet
        });
        // The edge tab: a roof edge (type, height, finish) or a connection.
        this.edges = proxy({
            loaded: false,
            options: { edges: [], connections: [] },
            kind: "edge", // "edge" (dakrand) or "connection" (aansluiting)
            edge: { type: "", height: "", product: 0 },
            connection: 0,
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
        if (this.props.buildup) {
            this.state.tab = "buildup";
        } else if (this.props.edges) {
            this.state.tab = "edges";
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
        });
    }

    // ------------------------------------------------------------ build-up
    async loadBuildup() {
        const data = await this.orm.call(
            "tectora.roof.project", "tectora_get_buildup_options", [[this.props.buildup.projectId]]
        );
        const b = this.buildup;
        b.options = data.options;
        b.margin = data.margin;
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
                lines.push({
                    label,
                    product,
                    subtotal: product.price * this.totalQuantity,
                });
            }
        };
        add("vapour", "Dampscherm", choice.vapour_id);
        add("insulation", "Isolatie", choice.insulation_id);
        add("membrane", "Dakbedekking", choice.membrane_id);
        return lines;
    }

    get buildupTotal() {
        return this.buildupLines.reduce((sum, line) => sum + line.subtotal, 0);
    }

    get canApplyBuildup() {
        const choice = this.buildupChoice;
        return Boolean(choice.vapour_id || choice.insulation_id || choice.membrane_id || this.buildup.sheets);
    }

    get sheetsTotal() {
        return this.buildup.preview.reduce((sum, sheet) => sum + sheet.area, 0);
    }

    onMarginInput(ev) {
        const value = parseFloat(String(ev.target.value).replace(",", "."));
        this.buildup.margin = value >= 0 ? value / 100 : 0;
        this.refreshSheets();
        this.refreshEdgeCorners();
    }

    toggleSheetDetails(checked) {
        this.buildup.details = checked;
    }

    toggleSheets(checked) {
        this.buildup.sheets = checked;
        this.refreshSheets();
        this.refreshEdgeCorners();
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
            const preview = await this.props.buildup.preview(this.selectedTargetKeys, b.margin);
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
            margin: this.buildup.margin,
        };
        this.props.close();
        await this.props.buildup.apply(choice, targetKeys);
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

    setConnection(value) {
        this.edges.connection = parseInt(value) || 0;
    }

    toggleEdgeCorners(checked) {
        this.edges.corners = checked;
        this.refreshEdgeCorners();
    }

    get edgeProductId() {
        return this.edges.kind === "edge" ? this.edges.edge.product : this.edges.connection;
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
        return { kind: e.kind, product_id: this.edgeProductId, corners: e.corners, geometry };
    }

    setSideValue(field, ev) {
        const value = parseFloat(String(ev.target.value).replace(",", "."));
        this.edges[field] = value > 0 ? Math.round(value * 100) / 100 : 0;
        this.edges[`${field}Changed`] = true;
        ev.target.value = this.edges[field];
    }

    get canApplyEdges() {
        return Boolean(this.edgeProductId || this.edges.widthChanged || this.edges.upstandChanged);
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
        const product = this.edgeProduct;
        if (!product) {
            return [];
        }
        const lines = [{
            key: "side",
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
        this.props.close();
        await this.props.edges.apply(choice, targetKeys, false);
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
    }

    selectAllTargets(select) {
        this.state.selectedTargets = select
            ? Object.fromEntries(this.targets.map((target) => [target.key, true]))
            : {};
        this.refreshSheets();
        this.refreshEdgeCorners();
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
