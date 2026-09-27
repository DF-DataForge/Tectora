/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { Component, onMounted, proxy, signal, t, useProps } from "@odoo/owl";

/**
 * Ask for the real length of one side of a shape.
 *
 * Two modes, which is what the "schaal de andere zijden mee" checkbox picks:
 *
 * - checked (calibration): the drawing is right but the map scale is off, so
 *   only `scale_m_per_px` changes. No point moves, which means the drawing
 *   stays exactly on top of the satellite image, and every other length,
 *   surface and the measurement grid follow proportionally.
 * - unchecked: only this side is wrong, so the geometry moves and the scale
 *   is left alone. The two neighbouring sides stretch along with the moved
 *   corner -- unavoidable, a closed polygon cannot change one side in
 *   isolation.
 */
export class RoofEdgeLengthDialog extends Component {
    static template = "tectora_roof.RoofEdgeLengthDialog";
    static components = { Dialog };
    props = useProps({
        title: t.string(),
        currentLength: t.number(),
        currentScale: t.number(),
        // "Lengte" for a side, "Omtrek" for a circle.
        lengthLabel: t.string().optional(),
        // Whether the fixed-corner selector applies (not for circles).
        allowAnchor: t.boolean().optional(),
        // 1-based corner numbers of this side, for the selector labels.
        startPoint: t.number().optional(),
        endPoint: t.number().optional(),
        onConfirm: t.function(),
        close: t.function(),
    });

    setup() {
        this.inputRef = signal.ref();
        this.state = proxy({
            value: this.props.currentLength.toFixed(2),
            scaleAll: true,
            anchor: "start",
        });
        onMounted(() => {
            const input = this.inputRef();
            if (input) {
                input.focus();
                input.select();
            }
        });
    }

    get lengthLabel() {
        return this.props.lengthLabel || "Lengte";
    }

    get target() {
        const value = parseFloat(String(this.state.value).replace(",", "."));
        return Number.isFinite(value) && value > 0 ? value : 0;
    }

    get factor() {
        return this.props.currentLength > 0
            ? this.target / this.props.currentLength
            : 0;
    }

    get newScale() {
        return this.props.currentScale * this.factor;
    }

    get scaleOutOfRange() {
        // A 100x rescale of the whole drawing is a typo, not a correction.
        return this.state.scaleAll && (this.factor < 0.01 || this.factor > 100);
    }

    get valid() {
        return this.target > 0 && !this.scaleOutOfRange;
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && this.valid) {
            ev.preventDefault();
            this.confirm();
        }
    }

    confirm() {
        if (!this.valid) {
            return;
        }
        this.props.onConfirm({
            length: this.target,
            scaleAll: this.state.scaleAll,
            anchor: this.state.anchor,
        });
        this.props.close();
    }
}
