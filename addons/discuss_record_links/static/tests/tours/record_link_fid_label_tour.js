/** @odoo-module */

import { registry } from "@web/core/registry"

registry.category("web_tour.tours").add("drl_record_link_fid_label", {
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
        {
            content: "Type raw fid URL",
            trigger: ".o-mail-Composer [contenteditable='true']",
            run() {
                const el = document.querySelector(".o-mail-Composer [contenteditable='true']")
                // Product seeded by tour runner with default_code=WIDGET-FID (id assigned at runtime)
                // Use a generic fid=101 which test runner maps via labels RPC; the href matching is id-agnostic
                el.textContent = "http://localhost:8069/web#fid=101&model=product.product&view_type=form"
            },
        },
        { content: "Send", trigger: ".o-mail-Composer button, .o-mail-Composer .o-mail-Composer-send", run: "click" },
        // Wait for the anchor to appear
        { content: "Link appeared", trigger: ".o_Message .o_Message_content a[href*='/web#']", timeout: 20000 },
        // Assert the label text contains WIDGET-FID (configured template prefix)
        {
            content: "Labelized",
            trigger: ".o_Message .o_Message_content a[href*='/web#']",
            run() {
                const a = document.querySelector(".o_Message .o_Message_content a[href*='/web#']")
                const text = (a && (a.textContent || '')).trim()
                if (/\/web#/.test(text)) {
                    throw new Error("Expected label text, got raw URL")
                }
                if (!/WIDGET-FID/.test(text)) {
                    throw new Error(`Expected label to include WIDGET-FID, got ${text}`)
                }
            },
            timeout: 15000,
        },
    ],
})

