import { registry } from '@web/core/registry'
import { BooleanToggleField, booleanToggleField } from '@web/views/fields/boolean_toggle/boolean_toggle_field'
import { useService } from '@web/core/utils/hooks'
import { useState } from '@odoo/owl'

export class BooleanToggleTooltipField extends BooleanToggleField {
    static template = "product_connect.BooleanToggleTooltipField"

    get computedTitle() {
        const recordData = this.props.record?.data || {}
        // noinspection JSUnresolvedReference - tech_result is a dynamic field from the record
        const techResult = recordData.tech_result

        if (this.props.readonly && this.props.name === 'is_scrap' && !techResult) {
            return 'Tech result required to mark as scrap'
        }
        return ''
    }

    setup() {
        super.setup()
        this.notification = useService('notification')
        this.state = useState({
            ...this.state,
            value: this.props.record.data[this.props.name] || false
        })
    }

    async onChange(value) {
        const recordData = this.props.record?.data || {}
        // noinspection JSUnresolvedReference - tech_result is a dynamic field from the record
        const techResult = recordData.tech_result

        // Check if trying to mark as scrap without tech_result
        if (value && this.props.name === 'is_scrap' && !techResult) {
            this.notification.add('Tech result required to mark as scrap', {
                type: 'warning',
                sticky: false,
            })
            // Don't update the value
            return
        }

        // Otherwise, update normally
        this.state.value = value
        const changes = { [this.props.name]: value }
        await this.props.record.update(changes, { save: this.props.autosave })
    }

    onDisabledClick(ev) {
        const recordData = this.props.record?.data || {}
        // noinspection JSUnresolvedReference - tech_result is a dynamic field from the record
        const techResult = recordData.tech_result

        // Only show notification if readonly, is_scrap field, and no tech_result
        if (this.props.readonly && this.props.name === 'is_scrap' && !techResult) {
            this.notification.add('Tech result required to mark as scrap', {
                type: 'warning',
                sticky: false,
            })
            ev.stopPropagation()
            ev.preventDefault()
        }
    }
}

// noinspection JSUnusedGlobalSymbols - extractProps is called by Odoo's field registry system
export const booleanToggleTooltipField = {
    ...booleanToggleField,
    component: BooleanToggleTooltipField,
    extractProps({ options }, dynamicInfo) {
        return {
            ...booleanToggleField.extractProps({ options }, dynamicInfo),
            autosave: "autosave" in options ? Boolean(options.autosave) : true,
            readonly: dynamicInfo.readonly,
        }
    },
}

registry.category('fields').add('boolean_toggle_tooltip', booleanToggleTooltipField)