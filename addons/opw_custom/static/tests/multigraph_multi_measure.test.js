/** @odoo-module */
 
// noinspection JSUnresolvedReference - Test accesses properties that should exist in full implementation  
import { test, expect } from "@odoo/hoot"
import { createTestMultigraphModel } from "@opw_custom/../tests/helpers/test_base"
import { MultigraphArchParser } from "@opw_custom/views/multigraph/multigraph_arch_parser"

test("@opw_custom MultigraphModel handles multiple measures", async () => {
    // Test that model preserves multiple measures
    const mockParams = {
        resModel: "product.template",
        fields: {
            initial_price_total: { type: "float", string: "Revenue Value" },
            initial_cost_total: { type: "float", string: "Cost Value" },
            initial_quantity: { type: "integer", string: "Units Processed" }
        },
        measures: [
            { fieldName: "initial_price_total", label: "Revenue Value", axis: "y", widget: "monetary" },
            { fieldName: "initial_cost_total", label: "Cost Value", axis: "y", widget: "monetary" },
            { fieldName: "initial_quantity", label: "Units Processed", axis: "y1", widget: null }
        ],
        axisConfig: {
            y: { position: "left", display: true },
            y1: { position: "right", display: true }
        }
    }

    const model = createTestMultigraphModel()
    model.setup(mockParams)

    // Verify multiple measures are preserved
    expect(model.customMeasures).toHaveLength(3)
    expect(model.customMeasures[0].fieldName).toBe("initial_price_total")
    expect(model.customMeasures[1].fieldName).toBe("initial_cost_total")
    expect(model.customMeasures[2].fieldName).toBe("initial_quantity")

    // Verify axis configuration
    expect(model.axisConfig.y.position).toBe("left")
    expect(model.axisConfig.y1.position).toBe("right")
})

test.skip("@opw_custom MultigraphArchParser extracts all measures from XML", () => {
    const archXml = `
        <graph string="Test" js_class="multigraph">
            <field name="date_field" interval="day"/>
            <field name="initial_price_total" type="measure" widget="monetary" string="Revenue"/>
            <field name="initial_cost_total" type="measure" widget="monetary" string="Cost"/>
            <field name="initial_quantity" type="measure" string="Quantity"/>
        </graph>
    `

    const fields = {
        date_field: { type: "date", string: "Date" },
        initial_price_total: { type: "float", string: "Revenue Value" },
        initial_cost_total: { type: "float", string: "Cost Value" },
        initial_quantity: { type: "integer", string: "Units Processed" }
    }

    const parser = new MultigraphArchParser()
    const xmlDoc = new DOMParser().parseFromString(archXml, "text/xml")
    const result = parser.parse(xmlDoc.documentElement, fields)

    // Verify all measures are extracted
    expect(result.measures).toHaveLength(3)
    expect(result.measures[0].fieldName).toBe("initial_price_total")
    expect(result.measures[0].widget).toBe("monetary")
    expect(result.measures[0].axis).toBe("y")

    expect(result.measures[1].fieldName).toBe("initial_cost_total")
    expect(result.measures[1].widget).toBe("monetary")
    expect(result.measures[1].axis).toBe("y")

    expect(result.measures[2].fieldName).toBe("initial_quantity")
    expect(result.measures[2].axis).toBe("y1") // Different axis for quantity
})
