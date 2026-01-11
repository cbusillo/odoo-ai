/** @odoo-module */
import { describe, expect, test } from "@odoo/hoot"
import { MultigraphArchParser } from "@product_connect/views/multigraph/multigraph_arch_parser"
import { parseXML } from "@web/core/utils/xml"

describe("MultigraphArchParser", () => {
    test("parses measures with axis configuration", () => {
        const arch = parseXML(`
            <graph js_class="multigraph" type="line">
                <field name="revenue" type="measure" axis="y" widget="monetary" string="Revenue"/>
                <field name="quantity" type="measure" axis="y1" string="Quantity"/>
            </graph>
        `)

        const fields = {
            revenue: { type: "monetary", string: "Revenue Amount" },
            quantity: { type: "integer", string: "Total Quantity" },
        }

        const parser = new MultigraphArchParser()
        const result = parser.parse(arch, fields)

        expect(result.measures).toHaveLength(2)
        expect(result.measures[0]).toEqual({
            fieldName: "revenue",
            axis: "y",
            widget: "monetary",
            label: "Revenue",
        })
        expect(result.measures[1]).toEqual({
            fieldName: "quantity",
            axis: "y1",
            widget: null,
            label: "Quantity",
        })

        expect(result.axisConfig).toEqual({
            y: { position: "left", display: true },
            y1: { position: "right", display: true },
        })
    })

    test("parses groupBy fields with intervals", () => {
        const arch = parseXML(`
            <graph js_class="multigraph" type="line">
                <field name="date" interval="month"/>
                <field name="partner_id"/>
                <field name="revenue" type="measure" axis="y"/>
            </graph>
        `)

        const fields = {
            date: { type: "date", string: "Date" },
            partner_id: { type: "many2one", string: "Partner" },
            revenue: { type: "monetary", string: "Revenue" },
        }

        const parser = new MultigraphArchParser()
        const result = parser.parse(arch, fields)

        expect(result.groupBy).toHaveLength(2)
        expect(result.groupBy[0]).toEqual({
            fieldName: "date",
            interval: "month",
        })
        expect(result.groupBy[1]).toEqual({
            fieldName: "partner_id",
        })
    })

    test("auto-detects measures when none specified", () => {
        const arch = parseXML(`<graph js_class="multigraph" type="line"></graph>`)

        const fields = {
            name: { type: "char", string: "Name" },
            amount: { type: "monetary", string: "Amount" },
            quantity: { type: "integer", string: "Quantity" },
            cost: { type: "float", string: "Cost" },
            description: { type: "text", string: "Description" },
        }

        const parser = new MultigraphArchParser()
        const result = parser.parse(arch, fields)

        expect(result.measures).toHaveLength(3)
        expect(result.measures.map(m => m.fieldName)).toEqual(["amount", "quantity", "cost"])
        expect(result.measures[0].widget).toBe("monetary")
    })

    test("handles empty arch gracefully", () => {
        // Use a well-formed graph root; parser should still handle no fields
        const arch = parseXML(`<graph js_class="multigraph" type="line" title="Test Chart" stacked="1"></graph>`)
        const fields = {}

        const parser = new MultigraphArchParser()
        const result = parser.parse(arch, fields)

        expect(result.title).toBe("Test Chart")
        expect(result.stacked).toBe(true)
        expect(Array.isArray(result.measures)).toBe(true)
        expect(Array.isArray(result.groupBy)).toBe(true)
    })

    test("uses field string as label fallback", () => {
        const arch = parseXML(`
            <graph js_class="multigraph" type="line">
                <field name="amount" type="measure"/>
            </graph>
        `)

        const fields = {
            amount: { type: "monetary", string: "Total Amount" },
        }

        const parser = new MultigraphArchParser()
        const result = parser.parse(arch, fields)

        expect(result.measures[0].label).toBe("Total Amount")
    })
})
