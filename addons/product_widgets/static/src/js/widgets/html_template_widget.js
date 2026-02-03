import { HtmlField, htmlField } from "@html_editor/fields/html_field"
import { onWillStart, useState } from "@odoo/owl"
import { _t } from "@web/core/l10n/translation"
import { registry } from "@web/core/registry"
import { useService } from "@web/core/utils/hooks"
import { withSequence } from "@html_editor/utils/resource"

export class HtmlTemplateWidget extends HtmlField {
    static template = "html_editor.HtmlField"
    static props = {
        ...HtmlField.props,
        propTags: { type: Array, optional: true },
        serverTagModel: { type: String, optional: true },
        serverTagMethod: { type: String, optional: true },
    }

    setup() {
        super.setup()
        this.orm = useService("orm")
        this.serverTagModel = this.props.serverTagModel || this.props.record.resModel
        this.serverTagMethod = this.props.serverTagMethod || "get_template_tags_list"
        this.state = useState({
            propTags: this.props.propTags || [],
            tags: [],
        })

        onWillStart(async () => {
            await this.loadTags()
        })
    }

    async loadTags() {
        try {
            const serverTags = await this.orm.call(
                this.serverTagModel,
                this.serverTagMethod,
                [],
            )
            this.state.tags = [...serverTags, ...this.state.propTags]
        } catch (error) {
            console.error(`Error while loading tags from ${this.serverTagModel}.${this.serverTagMethod}`, error)
        }
    }

    getConfig() {
        const config = super.getConfig()
        const tags = this.state.tags || []
        if (!tags.length) {
            return config
        }

        const resources = { ...config.resources }
        const commandId = "insert_template_tag"
        const categoryId = "template_tags"
        const userCommands = Array.isArray(resources.user_commands)
            ? [...resources.user_commands]
            : (resources.user_commands ? [resources.user_commands] : [])
        const categories = Array.isArray(resources.powerbox_categories)
            ? [...resources.powerbox_categories]
            : (resources.powerbox_categories ? [resources.powerbox_categories] : [])
        const items = Array.isArray(resources.powerbox_items)
            ? [...resources.powerbox_items]
            : (resources.powerbox_items ? [resources.powerbox_items] : [])

        if (!userCommands.some((command) => command.id === commandId)) {
            userCommands.push({
                id: commandId,
                title: _t("Insert template tag"),
                description: _t("Insert template tag"),
                icon: "fa-tag",
                run: ({ tag }) => this.insertTag(tag),
            })
        }

        if (!categories.some((category) => category.id === categoryId)) {
            categories.push(withSequence(200, { id: categoryId, name: _t("Template Tags") }))
        }

        tags.forEach((tag, index) => {
            items.push(withSequence(200 + index, {
                categoryId,
                commandId,
                title: tag,
                description: tag,
                icon: "fa-tag",
                commandParams: { tag },
            }))
        })

        return {
            ...config,
            resources: {
                ...resources,
                user_commands: userCommands,
                powerbox_categories: categories,
                powerbox_items: items,
            },
        }
    }

    insertTag(value) {
        const insert = this.editor?.shared?.dom?.insert
        if (insert) {
            insert(`{${value}}`)
        }
    }
}

export const htmlTemplateWidget = {
    ...htmlField,
    component: HtmlTemplateWidget,
}


registry.category("fields").add("html_template", htmlTemplateWidget)
