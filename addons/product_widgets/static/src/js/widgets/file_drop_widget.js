import { onWillStart, useState } from '@odoo/owl'
import { useService } from '@web/core/utils/hooks'
import { registry } from '@web/core/registry'
import { BinaryField, binaryField } from '@web/views/fields/binary/binary_field'

import pluralize from '@product_widgets/js/utils/pluralize'
import { resizeImage } from '@product_widgets/js/utils/image_utils'


export class FileDropWidget extends BinaryField {
    static template = "product_widgets.FileDropWidget"
    static props = {
        ...BinaryField.props,
    }

    setup() {
        super.setup()
        this.orm = useService('orm')
        this.notification = useService('notification')
        this.action = useService('action')

        this.state = useState({
            message: ""
        })
        this.isShopifySyncAvailable = false

        onWillStart(async () => {
            const modelRecords = await this.orm.searchRead(
                "ir.model",
                [["model", "=", "shopify.sync"]],
                ["id"],
                { limit: 1 },
            )
            this.isShopifySyncAvailable = modelRecords.length > 0
        })

        this.updateDropMessage()

        this.imageModelName = this.props.record.data[this.props.name].resModel
    }

    updateDropMessage(countToAdd = 0) {
        const fieldCountName = pluralize(this.props.name, 1) + '_count'
        let total
        if (fieldCountName) {
            total = this.props.record.data[fieldCountName]
        } else {
            const { count } = this.props.record.data[this.props.name]
            total = count + countToAdd
        }

        this.state.message = pluralize('Image', total, true)
    }

    async getHighestIndex(productId) {
        const existingImages = await this.orm.searchRead(this.imageModelName, [['product_tmpl_id', '=', productId]], ['sequence']);
        if (!existingImages.length) return 0

        const maxSequence = Math.max(...existingImages.map(record => record.sequence || 0));
        return Math.floor(maxSequence / 10);  // Convert back to index
    }


    async onDrop(ev) {
        ev.target.classList.add('drag-over')
        ev.preventDefault()
        ev.stopPropagation()
        if (ev.dataTransfer) {
            const { files } = ev.dataTransfer
            const uploadFiles = [...files].sort((a, b) =>
                a.name.localeCompare(b.name)
            )
            try {
                this.notification.add(`Resizing ${uploadFiles.length} Image(s)`, {
                    type: 'info',
                })
                const uploadedImageBase = await Promise.all(
                    uploadFiles.map(async (file) => {
                        if (!(file instanceof Blob)) {
                            throw new Error("The file is not a Blob.")
                        }
                        return resizeImage(file, 1920, 1920)
                    })
                )
                const highestIndex = await this.getHighestIndex(this.props.record.resId);

                const recordsToSend = uploadedImageBase.map((image, index) => ({
                    product_tmpl_id: this.props.record.resId,
                    image_1920: image,
                    initial_index: index + highestIndex + 1,
                    sequence: (index + highestIndex + 1) * 10,  // Use sequence for proper ordering
                    name: index + highestIndex + 1,
                }))
                this.notification.add(`Uploading ${recordsToSend.length} Image(s)`, {
                    type: 'info',
                })
                await this.batchUpload(recordsToSend)
                if (this.isShopifySyncAvailable) {
                    const syncRecords = await this.orm.create("shopify.sync", [{ mode: "export_changed_products" }])
                    await this.orm.call("shopify.sync", "run_async", [syncRecords])
                }
                await this.props.record.load()
                this.notification.add(`${recordsToSend.length} Image(s) uploaded successfully`, {
                    type: 'success',
                })

                this.updateDropMessage(recordsToSend.length)

            } catch (error) {
                console.error('Error uploading images:', error)
                this.notification.add('Failed to upload images', {
                    title: 'Error',
                    type: 'danger',
                })
            }
        } else {
            console.error('dataTransfer is not available')
        }
    }

    async batchUpload(records, batchSize = 5, maxConcurrent = 5) {
        const batchPromises = [];
        const activePromises = new Set();  // Track active uploads

        for (let i = 0; i < records.length; i += batchSize) {
            const batch = records.slice(i, i + batchSize);

            const uploadPromise = this.orm.create(this.imageModelName, batch, { context: { skip_immediate_sync: true } })
                .then(() => {
                    activePromises.delete(uploadPromise);
                })
                .catch((error) => {
                    activePromises.delete(uploadPromise);
                    console.error("Error uploading images:", error);
                    this.notification.add('Failed to upload images', {
                        title: 'Error',
                        type: 'danger',
                    });
                });

            batchPromises.push(uploadPromise);
            activePromises.add(uploadPromise);

            if (activePromises.size >= maxConcurrent) {
                await Promise.race(activePromises);
            }
        }

        await Promise.all(batchPromises);
    }


    onDragEnter(ev) {
        ev.preventDefault()
        ev.stopPropagation()
        ev.target.classList.remove('drag-over')
    }

    onDragLeave(ev) {
        ev.preventDefault()
        ev.stopPropagation()
        ev.target.classList.add('drag-over')

    }

    onDragOver(ev) {
        ev.preventDefault()
    }
}


export const fileDropWidget = {
    ...binaryField,
    component: FileDropWidget
}

registry.category('fields').add('file_drop', fileDropWidget)
