import { GraphController } from "@web/views/graph/graph_controller"
import { useService } from "@web/core/utils/hooks"

/**
 * @typedef {import("./multigraph_model").MultigraphModel} MultigraphModel
 */

export class MultigraphController extends GraphController {
    // noinspection JSUnusedGlobalSymbols - called by parent GraphController
    get measureOptions() {
        // Required by parent GraphController
        return []
    }

    setup() {
        this.orm = useService("orm")
        super.setup()
    }

    onModeClick(mode) {
        // Delegate to the renderer's onModeClick method
        if (this.renderer && this.renderer.onModeClick) {
            this.renderer.onModeClick(mode)
        }
    }
}
