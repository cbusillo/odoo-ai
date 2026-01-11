import { onWillStart, useState } from "@odoo/owl"
import { useService } from "@web/core/utils/hooks"
import { HtmlField, htmlField } from "@html_editor/fields/html_field"
import { registry } from "@web/core/registry"

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
        this.startWysiwyg = this.startWysiwyg.bind(this)
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

    async startWysiwyg(wysiwyg) {
        await super.startWysiwyg(wysiwyg)
        this.addInsertTagButton()
        this.addTemplateTagsCommands()

    }

    addInsertTagButton() {
        const insertTagButton = `
            <button class="o_codeview_btn btn btn-primary dropdown-toggle" type="button" data-bs-toggle="dropdown">
                <i class="fa fa-tags"></i>
            </button>
            <ul class="dropdown-menu">
                ${this.state.tags.map(tag => `
                    <li>
                         <a class="dropdown-item insert-tag-item" href="#">${tag}</a>
                    </li>
                `).join('')}
            </ul>
        `;

        const toolbar = this.wysiwyg.odooEditor.toolbar;  // Get the toolbar element
        const buttonGroup = document.createElement('div');
        buttonGroup.id = 'insert-tags-btn-group';
        buttonGroup.className = 'btn-group';
        buttonGroup.innerHTML = insertTagButton;
        toolbar.appendChild(buttonGroup);

        const items = buttonGroup.querySelectorAll('.insert-tag-item');
        items.forEach((item, index) => {
            item.addEventListener('click', () => {
                this.insertTag(this.state.tags[index]);
            });
        });
    }

    addTemplateTagsCommands() {
        this.state.tags.slice().reverse().forEach((tag, index) => {
            // noinspection JSUnusedGlobalSymbols
            this.wysiwyg.odooEditor.powerbox.commands.push({
                category: 'Template Tags',
                name: tag,
                priority: 10 + index,
                description: 'Insert template tag: ' + tag,
                fontawesome: 'fa-tag',
                callback: () => this.insertTag(tag),
            });
        });
    }

    insertTag(value) {
        this.wysiwyg.odooEditor.execCommand('insert', `{${value}}`);
    }
}

export const htmlTemplateWidget = {
    ...htmlField,
    component: HtmlTemplateWidget,
}


registry.category("fields").add("html_template", htmlTemplateWidget)
