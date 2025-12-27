/** @odoo-module */

import { registry } from "@web/core/registry"

registry.category("web_tour.tours").add("drl_record_link_label", {
    test: true,
    url: "/odoo",
    steps: () => [
        { content: "Wait client", trigger: ".o_web_client", timeout: 20000 },
        { content: "Open Discuss", trigger: ".o_app[data-menu-xmlid='mail.mail_menu_root']", run: "click" },
        {
            content: "Focus composer",
            trigger: ".o-mail-Composer [contenteditable='true']",
            run: "click",
            timeout: 20000
        },
        // Insert a link using our inline provider so we don't rely on knowing the product id in the front-end
        { content: "Type bracket", trigger: ".o-mail-Composer [contenteditable='true']", run: "text [ tproe2e widget" },
        { content: "Pick first suggestion", trigger: ".o-mail-Composer-suggestion", run: "click", timeout: 10000 },
        // Send message
        {
            content: "Send message",
            trigger: ".o-mail-Composer .o-mail-Composer-send, .o-mail-Composer button[title='Send']",
            run: "click",
            timeout: 10000
        },
        // Verify the last message's anchor label no longer shows the raw URL
        {
            content: "Labelized link in message",
            trigger: ".o_Message .o_Message_content a[href*='/web#']",
            run() {
                const a = document.querySelector(".o_Message .o_Message_content a[href*='/web#']")
                if (!a) throw new Error("message link not found")
                const text = (a.textContent || '').trim()
                if (/\/web#id=\d+&model=/.test(text)) {
                    throw new Error("link label not transformed; still shows raw URL")
                }
            },
            timeout: 15000,
        },
    ],
})

