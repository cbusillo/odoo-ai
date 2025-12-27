/** @odoo-module */
// noinspection JSUnresolvedReference - Test file stubs private methods for testing internal behavior
import { describe, expect, test, beforeEach } from "@odoo/hoot"
import { MultigraphModel } from "@product_connect/views/multigraph/multigraph_model"

describe("@product_connect MultigraphModel Data Processing", () => {
    let model
    let mockOrm

    beforeEach(() => {
        // noinspection JSCheckFunctionSignatures - Test uses manual mocking pattern
        model = new MultigraphModel()
        model.orm = mockOrm
    })

    test("processes multi-axis data with correct groupBy handling", async () => {
        mockOrm = {
            webReadGroup: async () => {
                // Simulate Odoo's response with interval suffix in key
                return {
                    groups: [
                        {
                            __domain: [["date", ">=", "2024-01-01"]],
                            "date:month": "January 2024", // Odoo returns with interval suffix
                            date: "2024-01-01",
                            revenue: 10000,
                            cost: 7000,
                            quantity: 50,
                        },
                        {
                            __domain: [["date", ">=", "2024-02-01"]],
                            "date:month": "February 2024",
                            date: "2024-02-01",
                            revenue: 15000,
                            cost: 9000,
                            quantity: 75,
                        },
                    ],
                }
            },
        }

        const params = {
            resModel: "product.template",
            fields: {
                date: { type: "date", string: "Date" },
                revenue: { type: "monetary", string: "Revenue" },
                cost: { type: "monetary", string: "Cost" },
                quantity: { type: "integer", string: "Quantity" },
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary", label: "Revenue" },
                { fieldName: "cost", axis: "y", widget: "monetary", label: "Cost" },
                { fieldName: "quantity", axis: "y1", widget: null, label: "Quantity" },
            ],
        }

        model.setup(params)
        model.orm = mockOrm
        model.metaData = {
            resModel: params.resModel,
            fields: params.fields,
            fieldAttrs: {},
            measures: ["revenue", "cost", "quantity"],
        }

        await model._loadData({
            context: {},
            domain: [],
            groupBy: ["date:month"],
            orderBy: [],
        })

        // Should use the interval key for labels
        expect(model.data.labels).toEqual(["January 2024", "February 2024"])
        expect(model.data.datasets).toHaveLength(3)

        // Check datasets have correct axis assignments
        const revenueDataset = model.data.datasets.find(ds => ds.fieldName === "revenue")
        const quantityDataset = model.data.datasets.find(ds => ds.fieldName === "quantity")

        expect(revenueDataset.yAxisID).toBe("y")
        expect(quantityDataset.yAxisID).toBe("y1")
    })

    test("handles groupBy without intervals correctly", async () => {
        mockOrm = {
            webReadGroup: async () => ({
                groups: [
                    {
                        __domain: [["partner_id", "=", 1]],
                        partner_id: [1, "Partner A"],
                        revenue: 5000,
                        cost: 3000,
                    },
                    {
                        __domain: [["partner_id", "=", 2]],
                        partner_id: [2, "Partner B"],
                        revenue: 8000,
                        cost: 4500,
                    },
                ],
            }),
        }

        const params = {
            resModel: "sale.order",
            fields: {
                partner_id: { type: "many2one", string: "Partner" },
                revenue: { type: "monetary", string: "Revenue" },
                cost: { type: "monetary", string: "Cost" },
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary", label: "Revenue" },
                { fieldName: "cost", axis: "y", widget: "monetary", label: "Cost" },
            ],
        }

        model.setup(params)
        model.orm = mockOrm
        model.metaData = {
            resModel: params.resModel,
            fields: params.fields,
            fieldAttrs: {},
            measures: ["revenue", "cost"],
        }

        await model._loadData({
            context: {},
            domain: [],
            groupBy: ["partner_id"],
            orderBy: [],
        })

        // Should extract partner names correctly
        expect(model.data.labels).toEqual(["Partner A", "Partner B"])
    })

    test("processes data with null/undefined values", async () => {
        mockOrm = {
            webReadGroup: async () => ({
                groups: [
                    {
                        __domain: [],
                        date: "2024-01-01",
                        revenue: 10000,
                        cost: null, // Null value
                        quantity: undefined, // Undefined value
                    },
                    {
                        __domain: [],
                        date: "2024-02-01",
                        revenue: 0, // Zero value
                        cost: 5000,
                        quantity: 100,
                    },
                ],
            }),
        }

        const params = {
            resModel: "product.template",
            fields: {
                date: { type: "date", string: "Date" },
                revenue: { type: "monetary", string: "Revenue" },
                cost: { type: "monetary", string: "Cost" },
                quantity: { type: "integer", string: "Quantity" },
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary" },
                { fieldName: "cost", axis: "y", widget: "monetary" },
                { fieldName: "quantity", axis: "y1", widget: null },
            ],
        }

        model.setup(params)
        model.orm = mockOrm
        model.metaData = {
            resModel: params.resModel,
            fields: params.fields,
            fieldAttrs: {},
            measures: ["revenue", "cost", "quantity"],
        }

        await model._loadData({
            context: {},
            domain: [],
            groupBy: ["date"],
            orderBy: [],
        })

        // Should handle null/undefined as 0
        const costDataset = model.data.datasets.find(ds => ds.fieldName === "cost")
        const quantityDataset = model.data.datasets.find(ds => ds.fieldName === "quantity")

        expect(costDataset.data).toEqual([0, 5000])
        expect(quantityDataset.data).toEqual([0, 100])
    })

    test("applies correct colors to datasets", async () => {
        mockOrm = {
            webReadGroup: async () => ({
                groups: [{
                    __domain: [],
                    date: "2024-01-01",
                    m1: 100,
                    m2: 200,
                    m3: 300,
                    m4: 400,
                    m5: 500,
                    m6: 600, // More than 5 measures to test color cycling
                }],
            }),
        }

        const measures = []
        const fields = { date: { type: "date", string: "Date" } }

        for (let i = 1; i <= 6; i++) {
            const fieldName = `m${i}`
            fields[fieldName] = { type: "integer", string: `Measure ${i}` }
            measures.push({ fieldName, axis: "y", widget: null, label: `M${i}` })
        }

        const params = {
            resModel: "test.model",
            fields,
            measures,
        }

        model.setup(params)
        model.orm = mockOrm
        model.metaData = {
            resModel: params.resModel,
            fields: params.fields,
            fieldAttrs: {},
            measures: measures.map(m => m.fieldName),
        }

        await model._loadData({
            context: {},
            domain: [],
            groupBy: ["date"],
            orderBy: [],
        })

        // Check colors are assigned
        expect(model.data.datasets).toHaveLength(6)

        // First 5 should have unique colors
        const firstFiveColors = model.data.datasets.slice(0, 5).map(ds => ds.backgroundColor)
        expect(new Set(firstFiveColors).size).toBe(5)

        // 6th should cycle back to first color
        expect(model.data.datasets[5].backgroundColor).toBe(model.data.datasets[0].backgroundColor)
    })

    test("formats different value types correctly", () => {
        // Test monetary formatting
        const monetaryDataset = { widget: "monetary" }
        expect(model.getFormattedValue(1234.56, monetaryDataset)).toBe("$1,234.56")
        expect(model.getFormattedValue(0, monetaryDataset)).toBe("$0.00")
        expect(model.getFormattedValue(1000000, monetaryDataset)).toBe("$1,000,000.00")

        // Test integer formatting
        const integerDataset = { widget: null }
        expect(model.getFormattedValue(1234, integerDataset)).toBe("1,234")
        expect(model.getFormattedValue(0, integerDataset)).toBe("0")

        // Test float formatting
        expect(model.getFormattedValue(1234.567, integerDataset)).toBe("1234.57")
        expect(model.getFormattedValue(0.123, integerDataset)).toBe("0.12")
    })

    test("handles empty groupBy correctly", async () => {
        mockOrm = {
            webReadGroup: async () => ({
                groups: [
                    {
                        __domain: [],
                        revenue: 25000,
                        cost: 15000,
                        __count: 4,
                    },
                ],
            }),
        }

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
        model.orm = mockOrm
        model.metaData = {
            resModel: params.resModel,
            fields: params.fields,
            fieldAttrs: {},
            measures: ["revenue", "cost"],
        }

        await model._loadData({
            context: {},
            domain: [],
            groupBy: [],
            orderBy: [],
        })

        // Should show "Total" as label
        expect(model.data.labels).toEqual(["Total"])
        expect(model.data.datasets[0].data).toEqual([25000])
        expect(model.data.datasets[1].data).toEqual([15000])
    })

    test("uses context groupbys when searchParams groupBy is empty", async () => {
        mockOrm = {
            webReadGroup: async (model, domain, fields, groupBy) => {
                // Verify the groupBy from context is used
                expect(groupBy).toEqual(["date:month"])

                return {
                    groups: [{
                        __domain: [],
                        "date:month": "January 2024",
                        revenue: 10000,
                    }],
                }
            },
        }

        const params = {
            resModel: "product.template",
            fields: {
                date: { type: "date", string: "Date" },
                revenue: { type: "monetary", string: "Revenue" },
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary" },
            ],
        }

        model.setup(params)
        model.orm = mockOrm
        model.metaData = {
            resModel: params.resModel,
            fields: params.fields,
            fieldAttrs: {},
            measures: ["revenue"],
        }

        await model._loadData({
            context: { graph_groupbys: ["date:month"] },
            domain: [],
            groupBy: [], // Empty groupBy
            orderBy: [],
        })

        expect(model.data.labels).toEqual(["January 2024"])
    })

    test("ensures dataPoints property exists for renderer", async () => {
        mockOrm = {
            webReadGroup: async () => ({
                groups: [{
                    __domain: [],
                    revenue: 10000,
                }],
            }),
        }

        const params = {
            resModel: "product.template",
            fields: {
                revenue: { type: "monetary", string: "Revenue" },
            },
            measures: [
                { fieldName: "revenue", axis: "y", widget: "monetary" },
            ],
        }

        model.setup(params)
        model.orm = mockOrm
        model.metaData = {
            resModel: params.resModel,
            fields: params.fields,
            fieldAttrs: {},
            measures: ["revenue"],
        }

        await model._loadData({
            context: {},
            domain: [],
            groupBy: [],
            orderBy: [],
        })

        // dataPoints should reference the same data structure
        expect(model.dataPoints).toBe(model.data)
        expect(model.dataPoints.datasets).not.toBe(undefined)
    })
})
