import { FormController } from '@web/views/form/form_controller'
import { registry } from '@web/core/registry'
import { onWillUnmount } from "@odoo/owl";


class MotorFormController extends FormController {
    setup() {
        super.setup()
        this.motorId = this.props.resId || null
        this.busService = this.env.services["bus_service"]
        if (this.motorId) {
            this.registerBus()
        } else {
            this.model.hooks.onWillSaveRecord = this.onWillSaveRecord.bind(this)
        }
        this.model.hooks.onRecordChanged = this.onRecordChanged.bind(this)

        onWillUnmount(this.unregisterBus.bind(this))
    }


    async onWillSaveRecord(record) {
        await super.onWillSaveRecord(...arguments)
        if (record.resId && !this.motorId) {
            this.motorId = record.resId
            this.registerBus()
        }
    }

    registerBus() {
        const channel = `motor_${this.motorId}`
        this.busService.addChannel(channel)
        this.busService.addEventListener('notification', this.onBusNotification.bind(this))
    }

    unregisterBus() {
        const channel = `motor_${this.motorId}`
        this.busService.deleteChannel(channel)
        this.busService.removeEventListener('notification', this.onBusNotification.bind(this))
    }

    onBusNotification({ detail: notifications }) {
        for (const { type, payload } of notifications) {
            if (type === 'notification' && payload.type === 'motor_product_update') {
                this.reloadProductFields().catch(console.error)
            }
        }
    }

    async reloadProductFields() {
        const fieldsToReload = [
            'products',
            'products_to_dismantle',
            'products_to_clean',
            'products_to_picture',
            'products_to_stock',
        ]
        await this.model.load({ fieldNames: fieldsToReload })
    }

    onRecordChanged(editedRecord, editedFields) {
        const editedData = editedRecord.data
        const editedFieldNames = Object.keys(editedFields)
        const requiredFieldsToSave = [
            'manufacturer',
            'stroke',
            'configuration',
            'color',
        ]
        const requiredFieldsToPrint = [
            'horsepower',
            'model',
            'serial_number',
            'year',
        ]
        const combinedRequiredFields = [
            ...requiredFieldsToSave,
            ...requiredFieldsToPrint]

        const allPrintFieldsHaveValues = this.allFieldsHaveValues(editedData,
            combinedRequiredFields)

        const changedFieldInFieldsToPrint = requiredFieldsToPrint.some(
            field => editedFieldNames.includes(field))

        const allSaveFieldsHaveValues = this.allFieldsHaveValues(editedData,
            requiredFieldsToSave)

        if (allPrintFieldsHaveValues && allSaveFieldsHaveValues &&
            changedFieldInFieldsToPrint) {
            this.printMotorLabels()
            return
        }

        if (allSaveFieldsHaveValues) {
            this.model.root.save()
        }
    }

    allFieldsHaveValues(data, fields) {
        return fields.every(
            field => data[field] !== undefined && data[field] !== null &&
                data[field] !== '' && data[field] !== 0 && data[field] !== false)
    }

    printMotorLabels() {
        this.model.root.save().then(() => {
            this.model.action.doActionButton({
                name: 'print_motor_labels',
                type: 'object',
                resModel: 'motor',
                resId: this.model.root.resId,
                resIds: [this.model.root.resId],
            }).then(() => {
                console.log('Motor labels printed')
            })

        })
    }
}

registry.category('views').add('motor_form', {
    ...registry.category('views').get('form'),
    Controller: MotorFormController,
})