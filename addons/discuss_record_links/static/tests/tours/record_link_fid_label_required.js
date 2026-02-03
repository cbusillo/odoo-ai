/** @odoo-module */

import { registry } from "@web/core/registry"

const findDiscussApplication = () => {
    const applicationEntries = Array.from(document.querySelectorAll(".o_app"))
    return applicationEntries.find((applicationEntry) => {
        const menuXmlId = applicationEntry.dataset.menuXmlid || ""
        const label = (applicationEntry.textContent || "").toLowerCase()
        return menuXmlId.startsWith("mail.") || label.includes("discuss")
    })
}

const isDiscussOpen = () =>
    Boolean(document.querySelector(".o-mail-Discuss, .o-mail-Thread"))
const isVisible = (element) => {
    if (!element) {
        return false
    }
    const style = window.getComputedStyle(element)
    if (style.display === "none" || style.visibility === "hidden") {
        return false
    }
    return element.getClientRects().length > 0
}
const composerSelectors = [
    ".o-mail-Composer [contenteditable='true']",
    ".o-mail-Composer textarea",
    ".o-mail-Composer input[type='text']",
    ".o-mail-Composer input[type='search']",
    "textarea.o-mail-Composer-input",
    "input.o-mail-Composer-input",
    "textarea.o-mail-ComposerInput",
    "input.o-mail-ComposerInput",
]
const composerSelector = composerSelectors.join(", ")
const getComposerInput = () => {
    for (const selector of composerSelectors) {
        const candidates = Array.from(document.querySelectorAll(selector))
        const visible = candidates.find(
            (element) => isVisible(element) && !element.disabled,
        )
        if (visible) {
            return visible
        }
    }
    return null
}
const isComposerVisible = () => Boolean(getComposerInput())
const composerStepTimeout = 40000
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

const setComposerValue = (value) => {
    const composerElement = getComposerInput()
    if (!composerElement) {
        throw new Error("Composer input not found")
    }
    if (
        composerElement instanceof HTMLInputElement ||
        composerElement instanceof HTMLTextAreaElement
    ) {
        composerElement.value = value
        composerElement.dispatchEvent(new Event("input", { bubbles: true }))
        composerElement.dispatchEvent(new Event("change", { bubbles: true }))
    } else {
        composerElement.textContent = value
        composerElement.dispatchEvent(new Event("input", { bubbles: true }))
    }
}

const getProductId = () => {
    try {
        const request = new XMLHttpRequest()
        request.open("POST", "/web/dataset/call_kw", false)
        request.setRequestHeader("Content-Type", "application/json")
        request.send(
            JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: {
                    model: "ir.config_parameter",
                    method: "get_param",
                    args: ["drl_product_id_fid_required"],
                    kwargs: {},
                },
                id: 1,
            }),
        )
        const response = JSON.parse(request.responseText || "{}")
        return response?.result || ""
    } catch {
        return ""
    }
}

const channelName = "DRL Tour"
const normalizedChannelName = channelName.toLowerCase()

const isActiveDiscussThread = () => {
    const activeEntry = document.querySelector(
        ".o-mail-DiscussSidebarChannel.o-active, .o-mail-DiscussSidebarSubchannel.o-active, .o-mail-DiscussSidebar-item.o-active, .o-mail-ThreadPreview.o-active, .o-mail-ThreadListItem.o-active",
    )
    if (!activeEntry) {
        return false
    }
    return (activeEntry.textContent || "")
        .trim()
        .toLowerCase()
        .includes(normalizedChannelName)
}

const findDiscussChannelByName = () => {
    const nameSelectors = [
        ".o-mail-DiscussSidebarChannel-itemName",
        ".o-mail-DiscussSidebarChannel-itemName span",
        ".o-mail-DiscussSidebarSubchannel .text-truncate",
    ]
    const nameNodes = Array.from(document.querySelectorAll(nameSelectors.join(",")))
    const directMatch = nameNodes.find((node) =>
        (node.textContent || "")
            .trim()
            .toLowerCase()
            .includes(normalizedChannelName),
    )
    if (directMatch) {
        const entry = directMatch.closest("button, a") || directMatch
        if (isVisible(entry)) {
            return entry
        }
    }
    const selectors = [
        ".o-mail-DiscussSidebarChannel",
        ".o-mail-DiscussSidebar-item",
        ".o-mail-DiscussSidebarItem",
        ".o-mail-ThreadPreview",
        ".o-mail-ThreadListItem",
        "[data-channel-id]",
        "[data-thread-id]",
    ]
    const entries = Array.from(document.querySelectorAll(selectors.join(",")))
    const match = entries.find((entry) => {
        if (!isVisible(entry)) {
            return false
        }
        if (entry.closest(".o-mail-DiscussSidebarMailbox")) {
            return false
        }
        return (entry.textContent || "").trim().includes(channelName)
    })
    if (match) {
        return match.closest("button, a") || match
    }
    return null
}

const findDiscussThreadEntry = () => {
    const selectors = [
        ".o-mail-DiscussSidebarChannel",
        ".o-mail-DiscussSidebar-item",
        ".o-mail-DiscussSidebarItem",
        ".o-mail-ThreadPreview",
        ".o-mail-ThreadListItem",
        "[data-channel-id]",
        "[data-thread-id]",
    ]
    for (const selector of selectors) {
        const entries = Array.from(document.querySelectorAll(selector))
        const visibleEntry = entries.find(
            (entry) => {
                if (!isVisible(entry)) {
                    return false
                }
                if (entry.closest(".o-mail-DiscussSidebarMailbox")) {
                    return false
                }
                const threadType = (
                    entry.dataset.threadType || entry.dataset.channelType || ""
                ).toLowerCase()
                return threadType !== "mailbox"
            },
        )
        if (visibleEntry) {
            return visibleEntry.closest("button, a") || visibleEntry
        }
    }
    return null
}

const expandDiscussCategories = () => {
    const togglers = Array.from(
        document.querySelectorAll(".o-mail-DiscussSidebarCategory-toggler"),
    )
    for (const toggler of togglers) {
        const expanded = toggler.getAttribute("aria-expanded")
        const category = toggler.closest(".o-mail-DiscussSidebarCategory")
        let isCollapsed = false
        if (expanded === "false") {
            isCollapsed = true
        } else if (expanded !== "true") {
            if (category && category.classList.contains("o-mail-DiscussSidebarCategory--collapsed")) {
                isCollapsed = true
            } else {
                const icon = toggler.querySelector(
                    ".o-mail-DiscussSidebarCategory-icon, .o-mail-DiscussSidebarCategory-chevronCompact, .fa, .oi",
                )
                if (
                    icon &&
                    (icon.classList.contains("oi-chevron-right") ||
                        icon.classList.contains("fa-chevron-right") ||
                        icon.classList.contains("o-icon-chevron-right"))
                ) {
                    isCollapsed = true
                }
            }
        }
        if (isCollapsed) {
            toggler.click()
        }
    }
}

const openDiscussThread = () => {
    if (isComposerVisible() && isActiveDiscussThread()) {
        return
    }
    expandDiscussCategories()
    const candidates = []
    const namedEntry = findDiscussChannelByName()
    if (namedEntry) {
        candidates.push(namedEntry)
    }
    const fallbackEntry = findDiscussThreadEntry()
    if (fallbackEntry && fallbackEntry !== namedEntry) {
        candidates.push(fallbackEntry)
    }
    if (!candidates.length) {
        throw new Error("Discuss thread not found")
    }
    for (const entry of candidates) {
        entry.click()
        if (isComposerVisible()) {
            return
        }
    }
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
            run() {
                if (isDiscussOpen()) {
                    return
                }
                const discussApplication = findDiscussApplication()
                if (!discussApplication) {
                    throw new Error("Discuss app not found")
                }
                discussApplication.click()
            },
        },
        {
            content: "Wait for Discuss channels",
            trigger: ".o-mail-DiscussSidebarChannel, .o-mail-DiscussSidebar-item",
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
                const productId = getProductId()
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
