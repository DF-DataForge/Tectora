/** @odoo-module **/

/**
 * Undo and redo for the plan: the document is one text, so a step back is the
 * text before it. No Odoo import.
 */
export class History {
    constructor(limit = 100) {
        this.limit = limit;
        this.past = [];
        this.future = [];
    }

    /** Remember the document as it is before a change. */
    push(text) {
        if (this.past[this.past.length - 1] === text) {
            return;
        }
        this.past.push(text);
        if (this.past.length > this.limit) {
            this.past.shift();
        }
        this.future = [];
    }

    get canUndo() {
        return this.past.length > 0;
    }

    get canRedo() {
        return this.future.length > 0;
    }

    /** The document to go back to, given the current one; null if none. */
    undo(current) {
        if (!this.past.length) {
            return null;
        }
        this.future.push(current);
        return this.past.pop();
    }

    redo(current) {
        if (!this.future.length) {
            return null;
        }
        this.past.push(current);
        return this.future.pop();
    }
}
