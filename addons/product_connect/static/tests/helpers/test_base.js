/** @odoo-module */
/**
 * Base test utilities for multigraph tests
 * Provides consistent setup similar to Python test base classes
 */

import { MultigraphModel } from "@product_connect/views/multigraph/multigraph_model"

/**
 * Create a properly configured MultigraphModel for testing
 * @param {Object} overrides - Optional overrides for mock objects
 * @returns {MultigraphModel} Configured model instance
 */
export function createTestMultigraphModel(overrides = {}) {
    const mockOrm = {
        webReadGroup: async () => ({
            groups: [
                {
                    __domain: [["date", ">=", "2024-01-01"]],
                    date: "2024-01-01",
                    revenue: 10000,
                    cost: 7000,
                    quantity: 50,
                },
            ],
        }),
        ...overrides.orm
    }

    const mockEnv = {
        services: {},
        ...overrides.env
    }

    const mockParams = {
        ...overrides.params
    }

    const mockServices = {
        orm: mockOrm,
        ...overrides.services
    }

    const model = new MultigraphModel(mockEnv, mockParams, mockServices)
    model.orm = mockOrm

    return model
}

// noinspection JSUnusedGlobalSymbols - testData exported for use by other test files
/**
 * Standard test data for consistent testing
 */
export const testData = {
    fields: {
        date: { type: "date", string: "Date" },
        revenue: { type: "monetary", string: "Revenue" },
        cost: { type: "monetary", string: "Cost" },
        quantity: { type: "integer", string: "Quantity" },
        name: { type: "char", string: "Name" }
    },

    measures: {
        simple: [
            { fieldName: "revenue", axis: "y", widget: "monetary", label: "Revenue" }
        ],

        multiple: [
            { fieldName: "revenue", axis: "y", widget: "monetary", label: "Revenue" },
            { fieldName: "cost", axis: "y", widget: "monetary", label: "Cost" },
            { fieldName: "quantity", axis: "y1", widget: null, label: "Qty" }
        ]
    },

    axisConfig: {
        y: { position: "left", display: true },
        y1: { position: "right", display: true }
    }
}
