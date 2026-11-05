/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";
import { GanttRenderer } from "@web_gantt/gantt_renderer";
import { onMounted, onPatched, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// How much taller than the standard gantt the team planner's blocks are.
const PILL_SCALE = 3;

// The gantt (Odoo 20) lays its rows out on named grid lines: the renderer
// carries them in this variable ("[r1]25px[r2]16px[r3]25px..."), which the
// cells and the row headers both use, and a block sits between two of them
// (grid-area: r3 / c1 / r4 / c25).
const ROWS_VAR = "--Gantt__GridRows-grid-template-rows";

// What this planner set itself, per renderer element, and the value the
// gantt had put there before: a re-render scales from the gantt's own
// layout again instead of scaling an already scaled one.
const applied = new WeakMap();

function lineNumber(value) {
    const match = /^r(\d+)$/.exec(String(value).trim());
    return match ? parseInt(match[1], 10) : null;
}

/** The gantt's own value of a variable, undoing what this planner set. */
function ownValue(renderer, name) {
    const current = renderer.style.getPropertyValue(name);
    const previous = (applied.get(renderer) || {})[name];
    return previous && current === previous.value ? previous.original : current;
}

function setScaled(renderer, name, original, value) {
    const state = applied.get(renderer) || {};
    const previous = state[name];
    if (
        previous &&
        previous.original === original &&
        previous.target === value &&
        renderer.style.getPropertyValue(name) === previous.value
    ) {
        // Already so: setting it again would only trigger the observer.
        return;
    }
    renderer.style.setProperty(name, value);
    state[name] = { original, target: value, value: renderer.style.getPropertyValue(name) };
    applied.set(renderer, state);
}

/**
 * Makes the project blocks PILL_SCALE times as high: the rows the blocks
 * sit on (the tracks between the lines of their grid area) are scaled in
 * the gantt's own row variable, so the row headers follow; empty rows and
 * the space between blocks keep the standard height.
 */
function enlargePills(root) {
    const renderer = root.matches(".o_gantt_renderer")
        ? root
        : root.querySelector(".o_gantt_renderer");
    if (!renderer) {
        return;
    }
    const rows = ownValue(renderer, ROWS_VAR);
    if (!rows) {
        root.classList.remove("o_tectora_tall");
        return;
    }
    const covered = new Set();
    for (const item of renderer.querySelectorAll(".o_gantt_pill_wrapper")) {
        const style = getComputedStyle(item);
        const start = lineNumber(style.gridRowStart);
        const end = lineNumber(style.gridRowEnd);
        if (start && end && end > start) {
            for (let track = start; track < end; track++) {
                covered.add(track);
            }
        }
    }
    const scaled = rows.replace(/\[r(\d+)\]\s*([\d.]+)px/g, (whole, track, size) =>
        covered.has(parseInt(track, 10)) ? `[r${track}]${parseFloat(size) * PILL_SCALE}px` : whole
    );
    setScaled(renderer, ROWS_VAR, rows, scaled);
    // The blocks themselves take the height of their rows (team_gantt.scss):
    // never taller than the row they are in, whatever the gantt sets.
    root.classList.toggle("o_tectora_tall", scaled !== rows);
}

/**
 * The team planner: a click on a project block opens its summary dialog at
 * once, instead of the small popover whose "Edit" button opens it, and the
 * blocks are three times as high as the standard gantt so they carry the
 * key data of their site on several lines. Everything else (drag, resize,
 * create in a cell) is the standard gantt.
 */
export class TectoraTeamGanttRenderer extends GanttRenderer {
    setup() {
        super.setup(...arguments);
        const enlarge = () => {
            for (const el of document.querySelectorAll(".o_tectora_team_gantt")) {
                enlargePills(el);
            }
        };
        // The gantt sets its rows once more right after a render (on
        // loading): scale again on the next frame and a moment later, once,
        // not on every change of the planner (watching its styles kept the
        // gantt from drawing the days that scroll into view).
        const timers = new Set();
        const enlargeSoon = () => {
            enlarge();
            const frame = requestAnimationFrame(() => {
                timers.delete(frame);
                enlarge();
            });
            timers.add(frame);
            const timeout = setTimeout(() => {
                timers.delete(timeout);
                enlarge();
            }, 300);
            timers.add(timeout);
        };
        onMounted(enlargeSoon);
        onPatched(enlargeSoon);
        onWillUnmount(() => {
            for (const timer of timers) {
                cancelAnimationFrame(timer);
                clearTimeout(timer);
            }
        });
        this.setupScissors();
    }

    // ------------------------------------------------------------- scissors
    // As in the Planning app's planner: hovering a block near a day boundary
    // shows a dashed line with scissors; a click there cuts the block in two
    // at the start of that day (tectora.roof.planning.action_tectora_split_at).

    setupScissors() {
        this.tectoraOrm = useService("orm");
        this.tectoraAction = useService("action");
        this.tectoraCut = null;
        const cutter = document.createElement("div");
        cutter.className = "o_tectora_cutter d-none";
        cutter.innerHTML = '<i class="oi" data-icon="content_cut"></i><span class="o_tectora_cutter_label"></span>';
        const hide = () => {
            cutter.classList.add("d-none");
            this.tectoraCut = null;
        };
        const onMove = (ev) => {
            const pill = ev.target.closest && ev.target.closest(".o_gantt_pill");
            // Not while a block is dragged or resized.
            const cut = pill && ev.buttons === 0 ? this.tectoraCutAt(pill, ev.clientX) : null;
            if (!cut) {
                return hide();
            }
            const rect = pill.getBoundingClientRect();
            cutter.style.left = `${cut.x}px`;
            cutter.style.top = `${rect.top}px`;
            cutter.style.height = `${rect.height}px`;
            cutter.querySelector(".o_tectora_cutter_label").textContent = cut.label;
            cutter.classList.remove("d-none");
            this.tectoraCut = { pill, day: cut.day };
        };
        // The cut aimed at when the button goes down: the click comes after
        // the press, which hides the scissors (a press may start a drag).
        const onPress = () => {
            this.tectoraPressedCut = this.tectoraCut;
            hide();
        };
        let root = null;
        onMounted(() => {
            root = document.querySelector(".o_tectora_team_gantt");
            if (!root) {
                return;
            }
            document.body.appendChild(cutter);
            root.addEventListener("mousemove", onMove);
            root.addEventListener("mouseleave", hide);
            root.addEventListener("mousedown", onPress, true);
        });
        onWillUnmount(() => {
            if (root) {
                root.removeEventListener("mousemove", onMove);
                root.removeEventListener("mouseleave", hide);
                root.removeEventListener("mousedown", onPress, true);
            }
            cutter.remove();
        });
    }

    /**
     * The day boundary nearest to ``clientX`` inside ``pill``, within a few
     * pixels: {x, day: "yyyy-MM-dd", label}, or null. The cells span the
     * gantt's whole period, so a moment maps linearly onto their width.
     */
    tectoraCutAt(pill, clientX) {
        const metaData = (this.props.model || this.model || {}).metaData || {};
        const start = metaData.globalStart || metaData.startDate;
        const stop = metaData.globalStop || metaData.stopDate;
        const cells = pill.closest(".o_gantt_cells");
        if (!start || !stop || !cells || !start.toMillis) {
            return null;
        }
        const area = cells.getBoundingClientRect();
        const span = stop.toMillis() - start.toMillis();
        if (span <= 0 || area.width <= 0) {
            return null;
        }
        const toX = (moment) => area.left + ((moment.toMillis() - start.toMillis()) / span) * area.width;
        const toMoment = (x) => start.plus({ milliseconds: ((x - area.left) / area.width) * span });
        const rect = pill.getBoundingClientRect();
        const EDGE = 10;
        // The midnights inside the block (not at its very edges).
        let day = toMoment(rect.left + EDGE).startOf("day").plus({ days: 1 });
        const last = toMoment(rect.right - EDGE);
        let best = null;
        while (day <= last) {
            const x = toX(day);
            const distance = Math.abs(x - clientX);
            if (x > rect.left + EDGE && x < rect.right - EDGE && distance <= 12
                && (!best || distance < best.distance)) {
                best = { x, distance, day };
            }
            day = day.plus({ days: 1 });
        }
        if (!best) {
            return null;
        }
        return {
            x: best.x,
            day: best.day.toFormat("yyyy-MM-dd"),
            label: `Knippen op ${best.day.setLocale("nl").toFormat("ccc d LLL")}`,
        };
    }

    async tectoraSplit(recordId, day) {
        await this.tectoraOrm.call("tectora.roof.planning", "action_tectora_split_at", [
            [recordId],
            day,
        ]);
        await this.tectoraAction.doAction({ type: "ir.actions.client", tag: "soft_reload" });
    }

    onPillClicked(ev, pill) {
        const record = pill && pill.record;
        // A click on the scissors cuts the block instead of opening it.
        const cut = this.tectoraPressedCut;
        this.tectoraPressedCut = null;
        const target = ev && ev.target && ev.target.closest && ev.target.closest(".o_gantt_pill");
        if (cut && record && record.id && target === cut.pill) {
            return this.tectoraSplit(record.id, cut.day);
        }
        if (record && record.id && typeof this.props.openDialog === "function") {
            if (this.popover && this.popover.isOpen) {
                this.popover.close();
            }
            this.props.openDialog({ resId: record.id });
            return;
        }
        return super.onPillClicked(ev, pill);
    }
}

/**
 * The team planner's controller: "Weer vernieuwen" next to the gantt's own
 * buttons fetches the weather forecasts now (they are fetched every morning
 * too) and reloads the planner.
 */
export class TectoraTeamGanttController extends ganttView.Controller {
    // The gantt's own buttons, which ours are added to.
    static tectoraButtons = ganttView.buttonTemplate;

    setup() {
        super.setup(...arguments);
        this.tectoraOrm = useService("orm");
        this.tectoraAction = useService("action");
    }

    async onTectoraRefreshWeather() {
        const action = await this.tectoraOrm.call(
            "tectora.roof.planning",
            "action_tectora_refresh_weather",
            [[]]
        );
        await this.tectoraAction.doAction(action);
    }
}

export const tectoraTeamGanttView = {
    ...ganttView,
    Controller: TectoraTeamGanttController,
    Renderer: TectoraTeamGanttRenderer,
};
// Only when the gantt takes its buttons from a template (as the other views
// do); without one the planner keeps the gantt's own buttons, and the
// forecasts are refreshed from the work blocks' list or form.
if (ganttView.buttonTemplate) {
    tectoraTeamGanttView.buttonTemplate = "tectora_roof_planning.TeamGanttButtons";
}

registry.category("views").add("tectora_team_gantt", tectoraTeamGanttView);
