import { registry } from "@web/core/registry"
import { graphView } from "@web/views/graph/graph_view"
import { parseXML } from "@web/core/utils/xml"
import { MultigraphArchParser } from "./multigraph_arch_parser"
import { MultigraphModel } from "./multigraph_model"
import { MultigraphRenderer } from "./multigraph_renderer"
import { MultigraphController } from "./multigraph_controller"

const GRAPH_ROOT_CLASS = "o_graph_view"

export const multigraphView = {
    ...graphView,
    type: "multigraph",
    display_name: "MultiGraph",
    icon: "fa fa-line-chart",
    // Ensure standard graph root class is present for selectors/tours
    className: `${GRAPH_ROOT_CLASS} o_multigraph_view`,
    multiRecord: true,
    buttonTemplate: "web.MultigraphView.Buttons",
    searchMenuTypes: ["filter", "groupBy", "comparison", "favorite"],
    ArchParser: MultigraphArchParser,
    Model: MultigraphModel,
    Renderer: MultigraphRenderer,
    Controller: MultigraphController,

    props(genericProps, view) {
        // Ensure we provide our Model/Renderer/ArchParser regardless of incoming view stub
        const baseProps = graphView.props(genericProps, {
            ...graphView,
            ArchParser: MultigraphArchParser,
            Model: MultigraphModel,
            Renderer: MultigraphRenderer,
            // Keep GraphView's default className ("o_graph_view") so tours/selectors work
            // and only override if the caller explicitly provides one.
            buttonTemplate: view?.buttonTemplate ?? "web.MultigraphView.Buttons",
            className: GRAPH_ROOT_CLASS,
        })

        // Extend/modify the modelParams for multigraph specifics
        let modelParams = { ...baseProps.modelParams }

        if (!genericProps.state) {
            try {
                const rawArch = genericProps.arch
                const fields = genericProps.fields || {}
                const archNode = typeof rawArch === "string" ? parseXML(rawArch) : rawArch

                if (archNode) {
                    const parser = new MultigraphArchParser()
                    const archInfo = parser.parse(archNode, fields)

                    modelParams = {
                        ...modelParams,
                        measures: archInfo.measures || [],
                        axisConfig: archInfo.axisConfig || {},
                        mode: "line", // Default to line for multigraph
                        title: archInfo.title || "MultiGraph",
                    }
                }
            } catch (e) {
                // Gracefully fall back to base props if parsing fails
                // Intentionally no rethrow to keep props generation resilient in tests
            }
        }

        return { ...baseProps, modelParams }
    },
}

registry.category("views").add("multigraph", multigraphView)
