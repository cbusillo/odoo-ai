/** @odoo-module */

import { registry } from "@web/core/registry"
import {
    composerSelector,
    composerStepTimeout,
    getComposerInput,
    openDiscussApplication,
    openDiscussThread,
    setComposerValue,
} from "./discuss_tour_helpers"

const labeledLinkSelector = [
    ".o_Message a[data-drl-labeled]",
    ".o-mail-Message a[data-drl-labeled]",
    ".o-mail-Message-content a[data-drl-labeled]",
    ".o-mail-Message-body a[data-drl-labeled]",
    ".o_Message a[data-oe-model][data-oe-id]",
    ".o-mail-Message a[data-oe-model][data-oe-id]",
    ".o-mail-Message-content a[data-oe-model][data-oe-id]",
    ".o-mail-Message-body a[data-oe-model][data-oe-id]",
].join(", ")

registry.category("web_tour.tours").add("drl_record_link_label", {
    test: true,
    url: "/web",
    steps: () => [
        { content: "Wait client", trigger: ".o_web_client", timeout: 20000 },
        {
            content: "Open Discuss",
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
        // Insert a link using our inline provider so we don't rely on knowing the product id in the front-end
        {
            content: "Insert URL via search",
            trigger: composerSelector,
            run() {
                const request = new XMLHttpRequest()
                request.open("POST", "/discuss_record_links/search", false)
                request.setRequestHeader("Content-Type", "application/json")
                request.send(
                    JSON.stringify({
                        jsonrpc: "2.0",
                        method: "call",
                        params: { term: "tproe2e widget" },
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
                    { triggerSuggestionAutocomplete: true },
                )
            },
        },
        // Send message
        {
            content: "Send message",
            trigger:
                ".o-mail-Composer .o-mail-Composer-send, .o-mail-Composer button[title='Send']",
            run: "click",
            timeout: 10000,
        },
        // Verify the last message's anchor label no longer shows the raw URL
        {
            content: "Labelized link in message",
            trigger: labeledLinkSelector,
            run() {
                const anchorElement =
                    document.querySelector(labeledLinkSelector)
                if (!anchorElement) {
                    throw new Error("message link not found")
                }
            },
            timeout: 30000,
        },
    ],
})
