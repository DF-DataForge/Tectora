import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

/**
 * The projects overview, the start page of the Project app: key figures
 * over all projects of the painting projects, each opening the projects behind
 * it, and lists of projects that each open the project's dashboard.
 */
export class SchldrProjectOverview extends Component {
    static template = "schldr_paint.ProjectOverview";
    static components = { Layout };
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, loading: true });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call("project.project", "schldr_get_overview_data", []);
        this.state.loading = false;
    }

    /** The projects behind a figure, in the Projecten views. */
    async openProjects(ids, title) {
        if (!ids || !ids.length) {
            return;
        }
        const action = await this.orm.call(
            "project.project",
            "action_schldr_overview_open_projects",
            [ids, title]
        );
        return this.action.doAction(action);
    }

    /** The dashboard of one project. */
    async openProject(projectId) {
        const action = await this.orm.call("project.project", "action_open_dashboard", [
            [projectId],
        ]);
        return this.action.doAction(action);
    }

    openAllProjects() {
        return this.action.doAction("schldr_paint.action_schldr_projects");
    }

    barWidth(section, entry) {
        const max = Math.max(...section.items.map((item) => item.value), 1);
        return `${Math.max((entry.value / max) * 100, entry.value ? 4 : 0)}%`;
    }
}

registry.category("actions").add("schldr_project_overview", SchldrProjectOverview);
