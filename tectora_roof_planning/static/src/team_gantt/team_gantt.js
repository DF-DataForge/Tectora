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
const PILL_HEIGHT_VAR = "--Gantt__Pill-height";

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
    // The blocks' own height goes with their rows: scaled with them, back to
    // the gantt's when no row is scaled (never one without the other).
    const pillHeight = ownValue(renderer, PILL_HEIGHT_VAR);
    if (pillHeight) {
        setScaled(
            renderer,
            PILL_HEIGHT_VAR,
            pillHeight,
            scaled !== rows ? `${parseFloat(pillHeight) * PILL_SCALE}px` : pillHeight
        );
    }
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
        // The gantt also rewrites its row variable outside a render (on
        // loading, while a block is dragged), which put the rows back to the
        // standard height under blocks that stayed tall: any change of a
        // style in the planner scales again, at most once per frame. Setting
        // what is already set is skipped (setScaled), so this settles.
        let observer = null;
        let frame = null;
        const schedule = () => {
            if (frame === null) {
                frame = requestAnimationFrame(() => {
                    frame = null;
                    enlarge();
                });
            }
        };
        onMounted(() => {
            enlarge();
            observer = new MutationObserver(schedule);
            for (const el of document.querySelectorAll(".o_tectora_team_gantt")) {
                observer.observe(el, { attributes: true, attributeFilter: ["style"], subtree: true });
            }
        });
        onPatched(enlarge);
        onWillUnmount(() => {
            if (observer) {
                observer.disconnect();
            }
            if (frame !== null) {
                cancelAnimationFrame(frame);
            }
        });
    }

    onPillClicked(ev, pill) {
        const record = pill && pill.record;
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
