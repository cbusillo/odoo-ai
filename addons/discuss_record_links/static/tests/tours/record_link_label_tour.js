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
    composerElement.dispatchEvent(
        new KeyboardEvent("keyup", { bubbles: true, key: "[" }),
    )
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

registry.category("web_tour.tours").add("drl_record_link_label", {
    test: true,
    url: "/web",
    steps: () => [
        { content: "Wait client", trigger: ".o_web_client", timeout: 20000 },
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
                const anchorElement = document.querySelector(labeledLinkSelector)
                if (!anchorElement) {
                    throw new Error("message link not found")
                }
            },
            timeout: 30000,
        },
    ],
})
