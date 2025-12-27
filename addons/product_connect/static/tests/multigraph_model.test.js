/** @odoo-module */
import { describe, expect, test, beforeEach } from "@odoo/hoot";
import { MultigraphModel } from "@product_connect/views/multigraph/multigraph_model";

describe("@product_connect MultigraphModel", () => {
    let model;
    let mockOrm;

    beforeEach(() => {
        mockOrm = {
            webReadGroup: async () => ({
                groups: [
                    {
                        __domain: [["date", ">=", "2024-01-01"]],
                        date: "2024-01-01",
                        revenue: 10000,
                        cost: 7000,
                        quantity: 50,
                    },
                    {
                        __domain: [["date", ">=", "2024-02-01"]],
                        date: "2024-02-01",
                        revenue: 15000,
                        cost: 9000,
                        quantity: 75,
                    },
                ],
            }),
        };

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
            axisConfig: {
                y: { position: "left", display: true },
                y1: { position: "right", display: true },
            },
        };

        // noinspection JSCheckFunctionSignatures - Odoo model instantiation pattern
        model = new MultigraphModel();
        model.orm = mockOrm;
        model.setup(params);
    });

    test("loads multi-measure data correctly", async () => {
        const searchParams = {
            context: {},
            domain: [],
            groupBy: ["date"],
            orderBy: [],
        };

        await model.load(searchParams);

        expect(model.data.labels).toHaveLength(2);
        expect(model.data.datasets).toHaveLength(3);

        const revenueDataset = model.data.datasets[0];
        expect(revenueDataset.label).toBe("Revenue");
        expect(revenueDataset.data).toEqual([10000, 15000]);
        expect(revenueDataset.yAxisID).toBe("y");
        expect(revenueDataset.widget).toBe("monetary");
    });

    test("formats monetary values correctly", () => {
        const dataset = { widget: "monetary" };
        const formatted = model.getFormattedValue(1234.56, dataset);
        expect(formatted).toBe("$1,234.56");
    });

    test("formats integer values correctly", () => {
        const dataset = { widget: null };
        const formatted = model.getFormattedValue(1234, dataset);
        expect(formatted).toBe("1,234");
    });

    test("formats float values correctly", () => {
        const dataset = { widget: null };
        const formatted = model.getFormattedValue(1234.567, dataset);
        expect(formatted).toBe("1234.57");
    });

    test("assigns colors to datasets", async () => {
        await model.load({
            context: {},
            domain: [],
            groupBy: ["date"],
            orderBy: [],
        });

        expect(model.data.datasets[0].backgroundColor).toMatch(/rgba\(\d+,\s*\d+,\s*\d+,\s*[\d.]+\)/);
        expect(model.data.datasets[0].borderColor).toMatch(/rgb\(\d+,\s*\d+,\s*\d+\)/);

        const colors = model.data.datasets.map(ds => ds.backgroundColor);
        expect(new Set(colors).size).toBe(3);
    });

    test("handles empty data gracefully", async () => {
        mockOrm.webReadGroup = async () => ({ groups: [] });

        await model.load({
            context: {},
            domain: [],
            groupBy: ["date"],
            orderBy: [],
        });

        expect(model.data.labels).toEqual([]);
        expect(model.data.datasets).toEqual([]);
        expect(model.data.domains).toEqual([]);
    });

    test("formats group by values correctly", () => {
        const dateValue = "2024-01-15";
        const formatted = model._formatGroupByValue("date", dateValue);
        expect(formatted).toMatch(/1\/15\/2024|15\/1\/2024/);

        const m2oValue = [1, "Partner Name"];
        const formattedM2o = model._formatGroupByValue("partner_id", m2oValue);
        expect(formattedM2o).toBe("Partner Name");

        const undefinedValue = false;
        const formattedUndefined = model._formatGroupByValue("field", undefinedValue);
        expect(formattedUndefined).toBe("Undefined");
    });
});
