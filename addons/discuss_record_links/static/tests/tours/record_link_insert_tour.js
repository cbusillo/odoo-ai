/** @odoo-module */

import { registry } from "@web/core/registry"

registry.category("web_tour.tours").add("drl_record_link_insert", {
    test: true,
    url: "/web",
    steps: () => [
        {
            content: "Wait for web client",
            trigger: ".o_web_client",
            timeout: 20000,
        },
        {
            content: "Open Discuss app",
            trigger: ".o_app[data-menu-xmlid='mail.mail_menu_root']",
            run: "click",
        },
        {
            content: "Focus composer",
            trigger: ".o-mail-Composer [contenteditable='true']",
            run: "click",
            timeout: 20000,
        },
        {
            content: "Type bracket to open suggestions",
            trigger: ".o-mail-Composer [contenteditable='true']",
            run: "text [ pro widget",
        },
        {
            content: "Select first record suggestion",
            trigger: ".o-mail-Composer-suggestion",
            run: "click",
            timeout: 10000,
        },
        {
            content: "Inserted URL present in composer",
            trigger: ".o-mail-Composer [contenteditable='true']",
            run() {
                const el = document.querySelector(".o-mail-Composer [contenteditable='true']")
                const text = (el && (el.textContent || el.innerText || "")).trim()
                if (!/\/web#id=\d+&model=/.test(text)) {
                    throw new Error("Expected inserted record URL in composer text")
                }
            },
        },
    ],
})
