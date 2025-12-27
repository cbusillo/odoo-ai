/** @odoo-module */

import { describe, test, expect } from "@odoo/hoot"
import { SuggestionService } from "@mail/core/common/suggestion_service"

describe("@discuss_record_links Suggestion service patch", () => {
    test("adds '[' to supported delimiters", async () => {
        const svc = new SuggestionService({ services: {} })
        const delims = svc.getSupportedDelimiters()
        // The returned structure is an array of arrays of chars
        expect(delims.find((d) => Array.isArray(d) && d[0] === "[")).toBeTruthy()
    })

    test("searchSuggestions returns RecordLink items from cache", async () => {
        const svc = new SuggestionService({ services: {} })
        // Prime internal cache the way fetchSuggestions would
        svc.__recordLinkCache = [
            { id: 1, model: "product.product", label: "[SKU] Widget", group: "Products" },
            { id: 2, model: "motor", label: "F150 (2019)", group: "Motors" },
        ]
        const out = svc.searchSuggestions({ delimiter: "[", term: "wi" })
        expect(out.type).toBe("RecordLink")
        expect(out.suggestions).toHaveLength(2)
        expect(out.suggestions[0].label).toBe("[SKU] Widget")
    })
})

