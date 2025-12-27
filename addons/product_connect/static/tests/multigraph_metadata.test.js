/** @odoo-module */
 
// noinspection JSUnresolvedReference - Test file checks for planned features in development
import { describe, expect, test, beforeEach } from "@odoo/hoot"
import { createTestMultigraphModel } from "@product_connect/../tests/helpers/test_base"

describe("@product_connect MultigraphModel Metadata Handling", () => {
    let model

    beforeEach(() => {
        model = createTestMultigraphModel()
    })

    test("prevents f1.string error by ensuring all fields have string property", () => {
        const params = {
            resModel: "product.template",
            fields: {
                date: { type: "date" }, // Missing string property
                revenue: { type: "monetary", string: "Revenue" },
                cost: { type: "monetary" }, // Missing string property
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary", label: "Revenue" },
                { fieldName: "cost", axis: "y", widget: "monetary", label: "Cost" },
            ],
        }

        model.setup(params)
        const metaData = model._buildMetaData()

        // All fields should have string property
        expect(metaData.fields.date.string).not.toBe(undefined)
        expect(metaData.fields.revenue.string).toBe("Revenue")
        expect(metaData.fields.cost.string).not.toBe(undefined)
    })

    test("handles measure configuration correctly", () => {
        const params = {
            resModel: "product.template",
            fields: {
                revenue: { type: "monetary", string: "Revenue" },
                cost: { type: "monetary", string: "Cost" },
                quantity: { type: "integer", string: "Quantity" },
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary", label: "Revenue Label" },
                { fieldName: "cost", axis: "y", widget: "monetary", label: "Cost Label" },
                { fieldName: "quantity", axis: "y1", widget: null, label: "Qty" },
            ],
        }

        model.setup(params)

        // Check custom measure config is stored
        expect(model.customMeasureConfig.revenue).toEqual({
            axis: "y",
            widget: "monetary",
            label: "Revenue Label",
            type: undefined,
        })
        expect(model.customMeasureConfig.quantity.axis).toBe("y1")
    })

    test("converts measure array to parent format", () => {
        const params = {
            resModel: "product.template",
            fields: {
                amount: { type: "monetary", string: "Amount" },
            },
            measures: [
                { fieldName: "amount", axis: "y", widget: "monetary", label: "Total" },
            ],
        }

        model.setup(params)

        // Parent class expects measure field names as array
        expect(params.measures).toEqual(["amount"])
        expect(params.measureFields).toEqual(["amount"])
    })

    test("computes report measures with custom properties", () => {
        const params = {
            resModel: "product.template",
            fields: {
                revenue: { type: "monetary", string: "Revenue" },
                quantity: { type: "integer", string: "Quantity" },
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary", label: "Rev" },
                { fieldName: "quantity", axis: "y1", widget: null, label: "Qty" },
            ],
            fieldAttrs: {},
        }

        model.setup(params)
        model.metaData = {
            fields: params.fields,
            fieldAttrs: params.fieldAttrs,
            measures: ["revenue", "quantity"],
        }

        const reportMeasures = model._computeCustomReportMeasures()

        expect(reportMeasures.revenue.axis).toBe("y")
        expect(reportMeasures.revenue.widget).toBe("monetary")
        expect(reportMeasures.quantity.axis).toBe("y1")
    })

    test("preserves axis configuration", () => {
        const axisConfig = {
            y: { position: "left", display: true },
            y1: { position: "right", display: true },
        }

        const params = {
            resModel: "product.template",
            fields: {},
            axisConfig: axisConfig,
        }

        model.setup(params)
        const metaData = model._buildMetaData()

        expect(metaData.axisConfig).toEqual(axisConfig)
    })

    test("handles empty measures gracefully", () => {
        const params = {
            resModel: "product.template",
            fields: {
                name: { type: "char", string: "Name" },
            },
            measures: [],
        }

        model.setup(params)

        expect(model.customMeasureConfig).toEqual({})
        expect(model.data).not.toBe(undefined)
        expect(model.data.datasets).toEqual([])
    })

    test("initializes data structure to prevent template errors", () => {
        const params = {
            resModel: "product.template",
            fields: {},
        }

        model.setup(params)

        // Data should be initialized even before load
        expect(model.data).not.toBe(undefined)
        expect(model.data.datasets).toEqual([])
        expect(model.data.labels).toEqual([])
        expect(model.data.domains).toEqual([])
    })

    test("forces line mode for multiple measures", async () => {
        const params = {
            resModel: "product.template",
            fields: {
                revenue: { type: "monetary", string: "Revenue" },
                cost: { type: "monetary", string: "Cost" },
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary" },
                { fieldName: "cost", axis: "y", widget: "monetary" },
            ],
        }

        model.setup(params)
        model.metaData = {
            ...params,
            fieldAttrs: {},
            measures: ["revenue", "cost"]
        }

        await model.load({
            context: {},
            domain: [],
            groupBy: ["date"],
            orderBy: [],
        })

        expect(model.metaData.mode).toBe("line")
    })
})
