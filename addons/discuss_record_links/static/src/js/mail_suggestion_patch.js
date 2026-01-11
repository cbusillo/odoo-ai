import { patch } from "@web/core/utils/patch"
import { UseSuggestion } from "@mail/core/common/suggestion_hook"
// No need for router here; use canonical /web# URLs for consistency across models

// 2) Intercept selection to run our command instead of inserting raw text
const originalInsert = UseSuggestion.prototype.insert

function insertSuggestion(option) {
    // Intercept '/odoo' channel command selection to open the picker immediately
    const itemsType = this.state?.items?.type
    // Removed ChannelCommand path (/link). Inline provider only.
    // Inline RecordLink handler (triggered by "[")
    if (itemsType === "RecordLink" && option?.record) {
        const { id, model } = option.record
        const base = new URL(window.location.href).origin
        const url = `${base}/web#id=${id}&model=${model}&view_type=form`
        const pos = this.composer.selection.start
        const text = this.composer.text || ""
        const start = this.search?.position ?? pos
        const before = text.substring(0, start) // drop the '[' and term
        const after = text.substring(pos)
        const insert = `${url} `
        this.clearSearch()
        this.composer.text = before + insert + after
        const newPos = before.length + insert.length
        this.composer.selection.start = newPos
        this.composer.selection.end = newPos
        this.composer.forceCursorMove = true
        return
    }
    return originalInsert.call(this, option)
}

patch(UseSuggestion.prototype, {
    insert: insertSuggestion,
})
