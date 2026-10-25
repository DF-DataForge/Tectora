import { useBus } from "@web/core/utils/hooks";

/**
 * The blocks of a project (tasks, order list, ...) live side by side on the
 * dashboard and change each other's data: ticking off the order list ticks
 * off its task, for instance. After every change a block announces it on the
 * global bus; the other blocks of the same project reload.
 */
export const PROJECT_BOARD_CHANGED = "TECTORA:PROJECT-BOARD-CHANGED";

export function notifyProjectBoardChanged(env, projectId, source) {
    env.bus.trigger(PROJECT_BOARD_CHANGED, { projectId, source });
}

/** Call `reload` when another block changed data of the project `getProjectId()`. */
export function useProjectBoardChanged(env, getProjectId, source, reload) {
    useBus(env.bus, PROJECT_BOARD_CHANGED, ({ detail }) => {
        if (detail.source !== source && detail.projectId === getProjectId()) {
            reload();
        }
    });
}
