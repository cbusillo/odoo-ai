import { patch } from "@web/core/utils/patch"
import { Message } from "@mail/core/common/message"
function parseInternalUrl(href) {
    try {
        const url = new URL(href, window.location.origin)
        if (url.hash?.startsWith("#")) {
            const params = new URLSearchParams(url.hash.slice(1))
            const id = Number(params.get("id") || params.get("fid"))
            const model = params.get("model")
            if (id && model) return { id, model }
        }
        const parts = url.pathname.split("/").filter(Boolean)
        const idx = parts.indexOf("odoo")
        if (idx >= 0 && parts.length >= idx + 3) {
            const model = decodeURIComponent(parts[idx + 1])
            const id = Number(parts[idx + 2])
            if (id && model) return { id, model }
        }
    } catch {}
    return {}
}

function linkifyInternalUrls(root) {
    try {
        const re = /(https?:\/\/\S+\/(?:web#|odoo[#/])\S*)/gi
        const walker = document.createTreeWalker(
            root,
            NodeFilter.SHOW_TEXT,
            null,
        )
        const toProcess = []
        let node
        while ((node = walker.nextNode())) {
            if (node.nodeValue && re.test(node.nodeValue)) {
                toProcess.push(node)
            }
            re.lastIndex = 0
        }
        for (const textNode of toProcess) {
            const frag = document.createDocumentFragment()
            let txt = textNode.nodeValue || ""
            let m
            re.lastIndex = 0
            let lastIndex = 0
            while ((m = re.exec(txt))) {
                const url = m[1]
                const start = m.index
                const end = start + url.length
                if (start > lastIndex) {
                    frag.appendChild(
                        document.createTextNode(txt.slice(lastIndex, start)),
                    )
                }
                const a = document.createElement("a")
                a.setAttribute("href", url)
                a.textContent = url
                frag.appendChild(a)
                lastIndex = end
            }
            if (lastIndex < txt.length) {
                frag.appendChild(document.createTextNode(txt.slice(lastIndex)))
            }
            textNode.parentNode.replaceChild(frag, textNode)
        }
    } catch {
        /* best effort */
    }
}

/** @type {any} */
const originalPrepareMessageBody = Message.prototype.prepareMessageBody

const prepareMessageBody = function (bodyEl) {
        try {
            // Test-only guard: allow disabling labeler via URL param for red/green runs
            try {
                const q = new URLSearchParams(window.location.search || "")
                if (q.get("drl_disable") === "1") {
                    if (originalPrepareMessageBody) {
                        originalPrepareMessageBody.apply(this, arguments)
                    }
                    return
                }
            } catch {}
            if (originalPrepareMessageBody) {
                originalPrepareMessageBody.apply(this, arguments)
            }
            // Fallback: if core didn't linkify, attempt to convert bare URLs to anchors
            if (
                !bodyEl.querySelector(
                    'a[href*="/web#"], a[href*="/odoo#"], a[href*="/odoo/"]',
                )
            ) {
                linkifyInternalUrls(bodyEl)
            }
            const anchors = Array.from(
                bodyEl.querySelectorAll(
                    'a[href*="/web#"], a[href*="/odoo#"], a[href*="/odoo/"]',
                ),
            )
            if (!anchors.length) return
            const rpc = this.env.services.rpc
            const orm = this.env.services.orm
            const byModel = new Map()
            const targets = []
            for (const a of anchors) {
                const href = a.getAttribute("href") || ""
                const { id, model } = parseInternalUrl(href)
                if (!id || !model) continue
                targets.push([a, model, id])
                if (!byModel.has(model)) byModel.set(model, new Set())
                byModel.get(model).add(id)
            }
            if (!targets.length) return
            const payload = []
            for (const [model, idSet] of byModel.entries()) {
                for (const id of idSet) payload.push({ model, id })
            }
            const applyLabels = (rows) => {
                const map = new Map(
                    (rows || []).map((r) => [`${r.model}:${r.id}`, r.label]),
                )
                for (const [a, model, id] of targets) {
                    const label = map.get(`${model}:${id}`)
                    if (!label) continue
                    a.textContent = label
                    a.setAttribute("data-oe-id", String(id))
                    a.setAttribute("data-oe-model", model)
                }
            }
            rpc("/discuss_record_links/labels", { targets: payload })
                .then((rows) => {
                    if (!rows || !rows.length) throw new Error("empty")
                    applyLabels(rows)
                })
                .catch(() => {
                    // Fallback: display_name
                    for (const [model, idSet] of byModel.entries()) {
                        const ids = Array.from(idSet)
                        orm.call(model, "read", [ids, ["display_name"]], {})
                            .then((rr) =>
                                applyLabels(
                                    rr.map((r) => ({
                                        model,
                                        id: r.id,
                                        label: r.display_name,
                                    })),
                                ),
                            )
                            .catch(() => {})
                    }
                })
        } catch (e) {
            // swallow to avoid Owl lifecycle crashes
        }
}

const messagePatch = {}
messagePatch.prepareMessageBody = prepareMessageBody

patch(Message.prototype, messagePatch)
