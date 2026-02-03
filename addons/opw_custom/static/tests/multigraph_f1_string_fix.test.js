/** @odoo-module */
 
import { describe, expect, test } from "@odoo/hoot"
import { MultigraphArchParser } from "@opw_custom/views/multigraph/multigraph_arch_parser"
import { parseXML } from "@web/core/utils/xml"
import { createTestMultigraphModel } from "@opw_custom/../tests/helpers/test_base"

describe("@opw_custom Multigraph f1.string Error Prevention", () => {
    test("arch parser always provides label for measures", () => {
        const arch = parseXML(`
            <graph js_class="multigraph" type="line">
                <field name="revenue" type="measure" axis="y"/>
                <field name="cost" type="measure" axis="y" string=""/>
                <field name="quantity" type="measure" axis="y1"/>
            </graph>
        `)

        const fields = {
            revenue: { type: "monetary", string: "Revenue Field" },
            cost: { type: "monetary" }, // Missing string
            quantity: { type: "integer", string: "" }, // Empty string
        }

        const parser = new MultigraphArchParser()
        const result = parser.parse(arch, fields)

        // All measures should have labels
        result.measures.forEach(measure => {
            expect(measure.label).not.toBe(undefined)
            expect(measure.label).not.toBe("")
            expect(measure.label).not.toBe(null)
            expect(measure.label).not.toBe(undefined)
        })

        // Check specific labels
        expect(result.measures[0].label).toBe("Revenue Field") // From field.string
        expect(result.measures[1].label).toBe("cost") // Fallback to field name
        expect(result.measures[2].label).toBe("quantity") // Fallback to field name
    })

    test("model setup properly initializes fields for metadata", () => {
        const model = createTestMultigraphModel()

        const params = {
            resModel: "product.template",
            fields: {
                date_field: { type: "date" }, // Missing string
                revenue: { type: "monetary", string: "Revenue" },
                cost: { type: "monetary", string: "" }, // Empty string
                quantity: { type: "integer", string: null }, // Null string
                margin: { type: "float" }, // Missing string
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary", label: "Revenue" },
                { fieldName: "cost", axis: "y", widget: "monetary", label: "Cost" },
            ],
        }

        model.setup(params)

        // Verify measures are properly set up
        expect(model.measures).toHaveLength(2)
        expect(model.measures[0].label).toBe("Revenue")
        expect(model.measures[1].label).toBe("Cost")

        // Verify fields are stored
        expect(model.metaData.fields).toBe(params.fields)
    })

    test("model handles measures without labels gracefully", () => {
        const model = createTestMultigraphModel()

        const params = {
            resModel: "product.template",
            fields: {
                amount: { type: "monetary" }, // No string
            },
            measures: [
                { fieldName: "amount", axis: "y", widget: "monetary" }, // No label, will use field name
            ],
        }

        model.setup(params)

        // Verify measure is set up with some label
        expect(model.measures).toHaveLength(1)
        expect(model.measures[0].fieldName).toBe("amount")
        // Label should fallback to field name when not provided
        expect(model.measures[0].label).toBe(undefined) // No label was provided
    })

    test("model processes data without failing when fields lack string", () => {
        const model = createTestMultigraphModel({
            orm: {
                webReadGroup: async () => ({
                    groups: [{
                        __domain: [],
                        "revenue:sum": 5000,
                        "cost:sum": 3000,
                        "quantity:sum": 25,
                    }],
                }),
            }
        })

        const params = {
            resModel: "product.template",
            fields: {
                revenue: { type: "monetary" }, // No string
                cost: { type: "monetary", string: null },
                quantity: { type: "integer", string: "" },
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary", label: "Revenue" },
                { fieldName: "cost", axis: "y", widget: "monetary", label: "Cost" },
                { fieldName: "quantity", axis: "y1", widget: null, label: "Quantity" },
            ],
        }

        model.setup(params)

        // Load data should not fail even with missing field strings
        return model.load({
            context: {},
            domain: [],
            groupBy: [],
            orderBy: [],
        }).then(() => {
            expect(model.data.datasets).toHaveLength(3)
            expect(model.data.datasets[0].data).toEqual([5000])
            expect(model.data.datasets[1].data).toEqual([3000])
            expect(model.data.datasets[2].data).toEqual([25])
        })
    })

    test("full integration test - no f1.string error", async () => {
        // This simulates the full flow that was causing the error
        const model = createTestMultigraphModel({
            orm: {
                webReadGroup: async () => ({
                    groups: [{
                        __domain: [],
                        "revenue:sum": 10000,
                        "cost:sum": 7000,
                    }],
                }),
            }
        })

        // Simulate arch parser output with potential missing labels
        const params = {
            resModel: "product.template",
            fields: {
                revenue: { type: "monetary" }, // No string property
                cost: { type: "monetary" },    // No string property
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary", label: "Revenue" }, // Add label
                { fieldName: "cost", axis: "y", widget: "monetary", label: "Cost" },    // Add label
            ],
        }

        model.setup(params)

        // Load data - should not throw error
        await model.load({
            context: {},
            domain: [],
            groupBy: [],
            orderBy: [],
        })

        // Verify data loaded successfully
        expect(model.data.datasets).toHaveLength(2)
        expect(model.data.datasets[0].label).toBe("Revenue")
        expect(model.data.datasets[1].label).toBe("Cost")
    })

    test("arch parser handles missing field definitions", () => {
        const arch = parseXML(`
            <graph js_class="multigraph" type="line">
                <field name="unknown_field" type="measure"/>
            </graph>
        `)

        const fields = {} // No field definitions

        const parser = new MultigraphArchParser()
        const result = parser.parse(arch, fields)

        // Should handle gracefully
        expect(result.measures).toHaveLength(1)
        expect(result.measures[0].label).toBe("unknown_field") // Fallback to field name
    })

    test("model integrates with parent class properly", () => {
        const model = createTestMultigraphModel()

        const params = {
            resModel: "product.template",
            fields: {
                amount: { type: "monetary", string: "Amount" },
            },
            measures: [
                { fieldName: "amount", axis: "y", widget: "monetary", label: "Amount" },
            ],
        }

        model.setup(params)

        // Verify our custom measures array is preserved
        expect(Array.isArray(model.measures)).toBe(true)
        expect(model.measures).toHaveLength(1)
        expect(model.measures[0].fieldName).toBe("amount")
        expect(model.measures[0].label).toBe("Amount")

        // Verify axis config is set
        expect(model.axisConfig).not.toBe(undefined)
    })
})
