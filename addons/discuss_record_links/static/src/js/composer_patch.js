import { patch } from "@web/core/utils/patch"
import { Composer } from "@mail/core/common/composer"

// Minimal extension: teach Composer how to render our custom suggestion type
// without altering any core behavior.
const _get = Object.getOwnPropertyDescriptor(Composer.prototype, "navigableListProps")?.get

patch(Composer.prototype, {
    get navigableListProps() {
        const props = _get ? _get.call(this) : {}
        const items = this.suggestion?.state.items
        if (!items || items.type !== "RecordLink") {
            return props
        }
        const base = {
            anchorRef: this.inputContainerRef.el,
            position: this.env.inChatter ? "bottom-fit" : "top-fit",
            onSelect: (ev, option) => {
                this.suggestion.insert(option)
                this.markEventHandled(ev, "composer.selectSuggestion")
            },
            isLoading: !!this.suggestion.search.term && this.suggestion.state.isFetching,
        }
        return {
            ...base,
            options: items.suggestions.map((s) => ({
                label: s.label,
                record: { id: s.id, model: s.model },
                classList: "o-mail-Composer-suggestion",
            })),
        }
    },
})

