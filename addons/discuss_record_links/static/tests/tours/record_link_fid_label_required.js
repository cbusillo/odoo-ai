/** @odoo-module */

import { registry } from "@web/core/registry"

// Red test: load with drl_disable=1 so the labeler is disabled, but assert label is present.
// This should fail until the labeler is enabled (green run without the flag).
registry.category("web_tour.tours").add("drl_record_link_fid_label_required", {
    test: true,
    url: "/web?drl_disable=1",
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
                el.textContent = "http://localhost:8069/web#fid=101&model=product.product&view_type=form"
            },
        },
        { content: "Send", trigger: ".o-mail-Composer button, .o-mail-Composer .o-mail-Composer-send", run: "click" },
        { content: "Link present", trigger: ".o_Message .o_Message_content a[href*='/web#']", timeout: 20000 },
        {
            content: "Expect label (should fail when disabled)",
            trigger: ".o_Message .o_Message_content a[href*='/web#']",
            run() {
                const a = document.querySelector(".o_Message .o_Message_content a[href*='/web#']")
                const text = (a && (a.textContent || '')).trim()
                if (/\/web#/.test(text)) {
                    throw new Error("Expected label text, got raw URL (RED as intended)")
                }
            },
            timeout: 15000,
        },
    ],
})
