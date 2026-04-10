import { registry } from '@web/core/registry'
import { BadgeSelectionField, badgeSelectionField } from '@web/views/fields/badge_selection/badge_selection_field'

export class ResettableBadgeSelectionField extends BadgeSelectionField {
    static template = "marine_motors.ResettableBadgeSelectionWidget"
    static props = {
        ...BadgeSelectionField.props,
    }

    resetValue() {
        this.props.record.update({ [this.props.name]: false })
    }
}

export const resettableBadgeSelectionField = {
    ...badgeSelectionField,
    component: ResettableBadgeSelectionField,
}

registry.category('fields').add('resettable_selection_badge', resettableBadgeSelectionField)
