import { SuggestionService } from "@mail/core/common/suggestion_service"
import { _t } from "@web/core/l10n/translation"
import { patch } from "@web/core/utils/patch"
import { rpc } from "@web/core/network/rpc"

patch(SuggestionService.prototype, {
    getSupportedDelimiters(thread) {
        const res = super.getSupportedDelimiters(thread)
        const out = res.slice()
        out.push(["["])
        return out
    },


    async fetchSuggestions({ delimiter, term }, { abortSignal } = {}) {
        if (delimiter !== "[") {
            return super.fetchSuggestions(...arguments)
        }
        this.__recordLinkCache = []
        try {
            const data = await rpc("/discuss_record_links/search", { term: term || "" }, { silent: true, abortSignal })
            const items = Array.isArray(data?.suggestions) ? data.suggestions : []
            this.__recordLinkCache = items.map((s) => ({
                id: s.id,
                name: s.label,
                model: s.model,
                label: s.label,
                group: s.group || _t("Records"),
            }))
        } catch (e) {
            // ignore; keep empty cache
        }
        // Fallback: if server route not available (404) or returned nothing, use local search
        if (!this.__recordLinkCache.length) {
            const t = (term || "").trimStart().toLowerCase()
            let modelFilter = null
            let q = t
            const m = t.match(/^(pro|product|mot|motor)\s+(.*)$/)
            if (m) {
                modelFilter = (m[1] === 'pro' || m[1] === 'product') ? 'product.product' : 'motor'
                q = m[2] || ''
            }
            const pushPairs = (pairs, group, model) => {
                for (const [id, label] of pairs || []) {
                    this.__recordLinkCache.push({ id, name: label, model, label, group })
                }
            }
            try {
                if (!modelFilter || modelFilter === 'product.product') {
                    const pairs = await this.makeOrmCall('product.product', 'name_search', [q, [], 'ilike', 8], {}, { abortSignal })
                    pushPairs(pairs, _t('Products'), 'product.product')
                }
                if (!modelFilter || modelFilter === 'motor') {
                    const tokens = q.trim().split(/\s+/).filter(Boolean)
                    let domain = []
                    for (const tok of tokens) {
                        const or = ['|', '|', '|', '|',
                            ['motor_number', 'ilike', tok],
                            ['model', 'ilike', tok],
                            ['year', 'ilike', tok],
                            ['configuration', 'ilike', tok],
                            ['manufacturer', 'ilike', tok],
                        ]
                        domain = domain.length ? ['&', domain, or] : or
                    }
                    const rows = await this.makeOrmCall('motor', 'search_read', [domain, ['display_name'], 0, 8], {}, { abortSignal })
                    pushPairs((rows || []).map(r => [r.id, r.display_name]), _t('Motors'), 'motor')
                }
            } catch (e) {
                // ignore fallback errors
            }
        }
    },

    searchSuggestions({ delimiter, term }, { sort = false } = {}) {
        if (delimiter !== "[") {
            return super.searchSuggestions(...arguments)
        }
        const suggestions = this.__recordLinkCache || []
        // Group label already provided; keep order
        return { type: "RecordLink", suggestions }
    },
})
