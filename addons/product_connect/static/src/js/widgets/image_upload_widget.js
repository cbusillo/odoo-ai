import { onWillUpdateProps, useRef, useState } from '@odoo/owl'
import { registry } from '@web/core/registry'
import { BinaryField, binaryField } from '@web/views/fields/binary/binary_field'
import { ImageField } from '@web/views/fields/image/image_field'

import { resizeImage } from '@product_connect/js/utils/image_utils'

export class ImageUploadWidget extends BinaryField {
    static template = 'product_connect.ImageUploadWidget'
    static props = {
        ...BinaryField.props,
    }

    setup() {
        super.setup()
        this.fileInputRef = useRef('fileInput')
        this.state = useState({
            image: this.props.record.data.image_1920,
            size: this.getPreviewImageSize(),
        })
        onWillUpdateProps(this.onRecordChange)
    }

    onRecordChange(nextProps) {
        if (nextProps.record.resId !== this.props.record.resId) {
            this.state.image = nextProps.record.data.image_1920
            this.state.size = this.getPreviewImageSize()
        }
    }


    // noinspection JSUnusedGlobalSymbols
    getPreviewImageSize() {
        const viewportWidth = window.innerWidth
        if (viewportWidth <= 512) {
            return '128'
        } else if (viewportWidth <= 1024) {
            return '256'
        } else if (viewportWidth <= 1920) {
            return '512'
        } else {
            return '1024'
        }
    }

    async onImageUpload() {
        this.fileInputRef.el.click()
    }

    async onFileChange(ev) {
        if (!ev.target || !ev.target.files || !ev.target.files.length) {
            return
        }
        const file = ev.target.files[0]
        const data = await resizeImage(file, 1920, 1920)

        await this.props.record.update({ image_1920: data })
        await this.props.record.save()
        this.state.image = data
        this.state.size = this.getPreviewImageSize()

        ev.target.value = null

    }

    onClick() {
        this.onImageUpload().then()
    }
}


ImageUploadWidget.components = {
    ImageField
}

export const imageUploadWidget = {
    ...binaryField,
    component: ImageUploadWidget
}

registry.category('fields').add('image_upload', imageUploadWidget)