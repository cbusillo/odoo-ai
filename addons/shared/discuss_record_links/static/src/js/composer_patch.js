import { patch } from "@web/core/utils/patch"
import { Composer } from "@mail/core/common/composer"
// Minimal extension: teach Composer how to render our custom suggestion type
// without altering any core behavior.
const originalNavigableListProps = Object.getOwnPropertyDescriptor(
    Composer.prototype,
    "navigableListProps"
)?.get

const getNavigableListProps = function () {
    const props = originalNavigableListProps ? originalNavigableListProps.call(this) : {}
    const items = this.suggestion?.state.items
    if (!items || items.type !== "RecordLink") {
        return props
    }
    props.options = items.suggestions.map((suggestion) => ({
        label: suggestion.label,
        record: { id: suggestion.id, model: suggestion.model },
        classList: "o-mail-Composer-suggestion",
    }))
    return props
}

const composerPatch = {}
Object.defineProperty(composerPatch, "navigableListProps", {
    configurable: true,
    enumerable: true,
    get: getNavigableListProps,
})

patch(Composer.prototype, composerPatch)
