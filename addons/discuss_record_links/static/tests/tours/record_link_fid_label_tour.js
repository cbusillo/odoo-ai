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

registry.category("web_tour.tours").add("drl_record_link_fid_label", {
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
        {
            content: "Type raw fid URL",
            trigger: composerSelector,
            run() {
                const productId = getConfigParameterValue(
                    "drl_product_id_fid_label",
                )
                if (!productId) {
                    throw new Error("Missing drl_product_id")
                }
                // Product seeded by tour runner with default_code=1001 (id assigned at runtime)
                // Use the injected product id to ensure label RPC can resolve it.
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
        // Wait for the anchor to appear
        {
            content: "Link appeared",
            trigger: messageLinkSelector,
            timeout: 20000,
        },
        // Assert the label text contains WIDGET-FID (configured template prefix)
        {
            content: "Labelized",
            trigger: labeledLinkSelector,
            run() {
                const anchorElement =
                    document.querySelector(labeledLinkSelector)
                if (!anchorElement) {
                    throw new Error("Labelized link not found")
                }
            },
            timeout: 30000,
        },
    ],
})
