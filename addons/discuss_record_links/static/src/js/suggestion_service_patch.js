import { SuggestionService } from "@mail/core/common/suggestion_service"
import { _t } from "@web/core/l10n/translation"
import { patch } from "@web/core/utils/patch"
import { rpc } from "@web/core/network/rpc"

const originalGetSupportedDelimiters = SuggestionService.prototype.getSupportedDelimiters
const originalFetchSuggestions = SuggestionService.prototype.fetchSuggestions
const originalSearchSuggestions = SuggestionService.prototype.searchSuggestions

const getSupportedDelimiters = function (thread, env) {
    const supportedDelimiters = originalGetSupportedDelimiters
        ? originalGetSupportedDelimiters.call(this, thread, env)
        : []
    const updatedDelimiters = supportedDelimiters.slice()
    updatedDelimiters.push(["["])
    return updatedDelimiters
}

const fetchSuggestions = async function ({ delimiter, term }, { thread, abortSignal } = {}) {
    if (delimiter !== "[") {
        if (originalFetchSuggestions) {
            return originalFetchSuggestions.apply(this, arguments)
        }
        return
    }
    void thread
    this.__recordLinkCache = []
    try {
        const data = await rpc("/discuss_record_links/search", { term: term || "" }, { silent: true, abortSignal })
        const items = Array.isArray(data?.suggestions) ? data.suggestions : []
        this.__recordLinkCache = items.map((suggestion) => ({
            id: suggestion.id,
            name: suggestion.label,
            model: suggestion.model,
            label: suggestion.label,
            group: suggestion.group || _t("Records"),
        }))
    } catch {
        // ignore; keep empty cache
    }
    // Fallback: if server route not available (404) or returned nothing, use local search
    if (!this.__recordLinkCache.length) {
        const normalizedTerm = (term || "").trimStart().toLowerCase()
        let modelFilter = null
        let query = normalizedTerm
        const match = normalizedTerm.match(/^(pro|product|mot|motor)\s+(.*)$/)
        if (match) {
            modelFilter = match[1] === "pro" || match[1] === "product" ? "product.product" : "motor"
            query = match[2] || ""
        }
        const appendPairs = (pairs, group, model) => {
            for (const [id, label] of pairs || []) {
                this.__recordLinkCache.push({ id, name: label, model, label, group })
            }
        }
        try {
            if (!modelFilter || modelFilter === "product.product") {
                const pairs = await this.makeOrmCall("product.product", "name_search", [query, [], "ilike", 8], {}, { abortSignal })
                appendPairs(pairs, _t("Products"), "product.product")
            }
            if (!modelFilter || modelFilter === "motor") {
                const tokens = query.trim().split(/\s+/).filter(Boolean)
                let domain = []
                for (const token of tokens) {
                    const orDomain = ["|", "|", "|", "|",
                        ["motor_number", "ilike", token],
                        ["model", "ilike", token],
                        ["year", "ilike", token],
                        ["configuration", "ilike", token],
                        ["manufacturer", "ilike", token],
                    ]
                    domain = domain.length ? ["&", domain, orDomain] : orDomain
                }
                const records = await this.makeOrmCall("motor", "search_read", [domain, ["display_name"], 0, 8], {}, { abortSignal })
                appendPairs((records || []).map((record) => [record.id, record.display_name]), _t("Motors"), "motor")
            }
        } catch {
            // ignore fallback errors
        }
    }
}

const searchSuggestions = function ({ delimiter, term }, { thread } = {}) {
    if (delimiter !== "[") {
        if (originalSearchSuggestions) {
            return originalSearchSuggestions.apply(this, arguments)
        }
        return { type: undefined, suggestions: [] }
    }
    void thread
    const suggestions = this.__recordLinkCache || []
    // Group label already provided; keep order
    return { type: "RecordLink", suggestions }
}

const suggestionServicePatch = {}
suggestionServicePatch.getSupportedDelimiters = getSupportedDelimiters
suggestionServicePatch.fetchSuggestions = fetchSuggestions
suggestionServicePatch.searchSuggestions = searchSuggestions

patch(SuggestionService.prototype, suggestionServicePatch)
