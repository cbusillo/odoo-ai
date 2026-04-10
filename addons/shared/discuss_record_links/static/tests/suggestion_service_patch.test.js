/** @odoo-module */

import { describe, test, expect } from "@odoo/hoot"
import { SuggestionService } from "@mail/core/common/suggestion_service"

const createSuggestionService = () => {
    const env = { inFrontendPortalChatter: false }
    const services = /** @type {any} */ ({
        orm: { silent: { call: () => Promise.resolve([]) } },
        "mail.store": { records: {} },
        "mail.composer": {},
    })
    const suggestionService = new SuggestionService(env, services)
    return { env, suggestionService }
}

describe("@discuss_record_links Suggestion service patch", () => {
    test("adds '[' to supported delimiters", async () => {
        const { env, suggestionService } = createSuggestionService()
        const supportedDelimiters = suggestionService.getSupportedDelimiters(undefined, env)
        // The returned structure is an array of arrays of chars
        expect(
            Boolean(
                supportedDelimiters.find(
                    (delimiter) => Array.isArray(delimiter) && delimiter[0] === "["
                )
            )
        ).toBe(true)
    })

    test("searchSuggestions returns RecordLink items from cache", async () => {
        const { suggestionService } = createSuggestionService()
        // Prime internal cache the way fetchSuggestions would
        suggestionService.__recordLinkCache = [
            { id: 1, model: "product.product", label: "[SKU] Widget", group: "Products" },
            { id: 2, model: "motor", label: "F150 (2019)", group: "Motors" },
        ]
        const result = suggestionService.searchSuggestions({ delimiter: "[", term: "wi" })
        expect(result.type).toBe("RecordLink")
        expect(result.suggestions).toHaveLength(2)
        expect(result.suggestions[0].label).toBe("[SKU] Widget")
    })
})
