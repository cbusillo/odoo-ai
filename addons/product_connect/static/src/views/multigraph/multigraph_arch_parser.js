import { visitXML } from "@web/core/utils/xml"
import { evaluateExpr } from "@web/core/py_js/py"

export class MultigraphArchParser {
    parse(arch, fields) {
        const result = {
            fields: {},
            measures: [],
            axisConfig: {},
            groupBy: [],
            title: arch.getAttribute("title") || "",
            disableLinking: arch.getAttribute("disable_linking") === "1",
            stacked: arch.getAttribute("stacked") === "1",
        }

        visitXML(arch, (node) => {
            if (node.tagName === "field") {
                const fieldName = node.getAttribute("name")

                if (node.getAttribute("type") === "measure") {
                    let axis = node.getAttribute("axis")
                    if (!axis) {
                        const contextExpr = node.getAttribute("context")
                        if (contextExpr) {
                            try {
                                const context = evaluateExpr(contextExpr)
                                const axisOverride = context?.["multigraph_axis"]
                                if (typeof axisOverride === "string") {
                                    axis = axisOverride
                                }
                            } catch (error) {
                                // Ignore context parsing errors and fall back to default axis.
                            }
                        }
                    }
                    axis = axis || "y"
                    const widget = node.getAttribute("widget")
                    const label = node.getAttribute("string") || fields[fieldName]?.string || fieldName

                    result.measures.push({
                        fieldName,
                        axis,
                        widget,
                        label,
                    })

                    result.fields[fieldName] = fields[fieldName]
                } else if (node.getAttribute("interval")) {
                    result.groupBy.push({
                        fieldName,
                        interval: node.getAttribute("interval"),
                    })
                    result.fields[fieldName] = fields[fieldName]
                } else {
                    result.groupBy.push({ fieldName })
                    result.fields[fieldName] = fields[fieldName]
                }
            }
        })

        if (!result.measures.length) {
            const numericFields = Object.entries(fields)
                .filter(([_, field]) => ["integer", "float", "monetary"].includes(field.type))
                .map(([name, field]) => ({
                    fieldName: name,
                    axis: "y",
                    widget: field.type === "monetary" ? "monetary" : null,
                    label: field.string || name,
                }))

            result.measures = numericFields.slice(0, 3)
            numericFields.slice(0, 3).forEach(({ fieldName }) => {
                result.fields[fieldName] = fields[fieldName]
            })
        }

        const axes = new Set(result.measures.map(m => m.axis))
        axes.forEach(axis => {
            result.axisConfig[axis] = {
                position: axis === "y" ? "left" : "right",
                display: true,
            }
        })

        return result
    }
}
