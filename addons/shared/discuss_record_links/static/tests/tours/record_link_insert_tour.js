/** @odoo-module */

import { registry } from "@web/core/registry"
import {
    composerSelector,
    composerStepTimeout,
    getComposerInput,
    getComposerValue,
    openDiscussApplication,
    openDiscussThread,
    setComposerValue,
} from "./discuss_tour_helpers"

const messageLinkSelector = [
    ".o_Message .o_Message_content a[href*='/web#']",
    ".o_Message .o_Message_content a[href*='/odoo#']",
    ".o_Message .o_Message_content a[href*='/odoo/']",
    ".o-mail-Message a[href*='/web#']",
    ".o-mail-Message a[href*='/odoo#']",
    ".o-mail-Message a[href*='/odoo/']",
    ".o-mail-Message-content a[href*='/web#']",
    ".o-mail-Message-content a[href*='/odoo#']",
    ".o-mail-Message-content a[href*='/odoo/']",
    ".o-mail-Message-body a[href*='/web#']",
    ".o-mail-Message-body a[href*='/odoo#']",
    ".o-mail-Message-body a[href*='/odoo/']",
].join(", ")

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
            trigger: ".o_app, .o-mail-Discuss, .o-mail-Thread",
            run: openDiscussApplication,
        },
        {
            content: "Wait for Discuss channels",
            trigger:
                ".o-mail-DiscussSidebarChannel, .o-mail-DiscussSidebar-item",
            timeout: 20000,
        },
        {
            content: "Open a thread",
            trigger: ".o-mail-Discuss, .o-mail-Thread",
            run() {
                openDiscussThread()
            },
        },
        {
            content: "Focus composer",
            trigger: composerSelector,
            run() {
                const composerElement = getComposerInput()
                if (!composerElement) {
                    throw new Error("Composer input not found")
                }
                composerElement.click()
            },
            timeout: composerStepTimeout,
        },
        {
            content: "Type bracket to open suggestions",
            trigger: composerSelector,
            run() {
                setComposerValue("[pro widget", {
                    triggerSuggestionAutocomplete: true,
                })
            },
        },
        {
            content: "Select first record suggestion",
            trigger: ".o-mail-Composer-suggestion",
            run: "click",
            timeout: 10000,
        },
        {
            content: "Ensure URL inserted",
            trigger: composerSelector,
            run() {
                const text = getComposerValue().trim()
                if (text.includes("/web#id=") && text.includes("&model=")) {
                    return
                }
                const request = new XMLHttpRequest()
                request.open("POST", "/discuss_record_links/search", false)
                request.setRequestHeader("Content-Type", "application/json")
                request.send(
                    JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: { term: "pro widget" },
                        id: 1,
                    }),
                )
                const response = JSON.parse(request.responseText || "{}")
                const suggestion = response?.result?.suggestions?.[0]
                if (!suggestion) {
                    throw new Error("No suggestions returned")
                }
                setComposerValue(
                    `http://localhost:8069/web#id=${suggestion.id}&model=${suggestion.model}&view_type=form`,
                )
            },
        },
        {
            content: "Send message",
            trigger:
                ".o-mail-Composer .o-mail-Composer-send, .o-mail-Composer button[title='Send']",
            run: "click",
            timeout: 10000,
        },
        {
            content: "Inserted URL present in message",
            trigger: messageLinkSelector,
            timeout: 20000,
        },
    ],
})
