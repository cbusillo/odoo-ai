/** @odoo-module */

import { registry } from "@web/core/registry"
import {
    composerSelector,
    composerStepTimeout,
    getConfigParameterValue,
    getComposerInput,
    openDiscussApplication,
    openDiscussThread,
    setComposerValue,
} from "./discuss_tour_helpers"

const messageTextSelectors = [
    ".o-mail-Message-body",
    ".o-mail-Message-content",
    ".o_Message_content",
    ".o_Message",
]

const messageContainsRawUrl = () => {
    const candidates = Array.from(
        document.querySelectorAll(messageTextSelectors.join(", ")),
    )
    return candidates.some((element) => {
        const text = element.textContent || ""
        return (
            text.includes("/web#") ||
            text.includes("/odoo#") ||
            text.includes("/odoo/")
        )
    })
}

// Load with drl_disable=1 so the labeler is disabled, then assert we keep the raw URL.
registry.category("web_tour.tours").add("drl_record_link_fid_label_required", {
    test: true,
    url: "/web?drl_disable=1",
    steps: () => [
        { content: "Wait client", trigger: ".o_web_client", timeout: 20000 },
        {
            content: "Disable labeler",
            trigger: ".o_web_client",
            run() {
                window.__drlDisable = true
            },
        },
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
        {
            content: "Type raw fid URL",
            trigger: composerSelector,
            run() {
                const productId = getConfigParameterValue(
                    "drl_product_id_fid_required",
                )
                if (!productId) {
                    throw new Error("Missing drl_product_id")
                }
                setComposerValue(
                    `http://localhost:8069/web#id=${productId}&model=product.product&view_type=form`,
                )
            },
        },
        {
            content: "Send",
            trigger:
                ".o-mail-Composer .o-mail-Composer-send, .o-mail-Composer button[title='Send']",
            run: "click",
        },
        {
            content: "Expect raw URL when disabled",
            trigger: ".o-mail-Message, .o_Message",
            run() {
                if (!messageContainsRawUrl()) {
                    throw new Error("Expected raw URL when labeler is disabled")
                }
            },
            timeout: 20000,
        },
    ],
})
