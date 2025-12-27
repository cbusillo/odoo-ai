/** @odoo-module */

import { describe, test, expect } from "@odoo/hoot"
import { Message } from "@mail/core/common/message"

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms))
}

describe("@discuss_record_links Message link label transformer", () => {
    test("replaces internal link text using /labels RPC", async () => {
        const container = document.createElement("div")
        const a = document.createElement("a")
        a.setAttribute("href", "/web#id=42&model=product.product&view_type=form")
        a.textContent = a.getAttribute("href") // looks like raw URL in body
        container.appendChild(a)

        const fakeEnv = {
            services: {
                rpc: async (route, payload) => {
                    expect(route).toBe("/discuss_record_links/labels")
                    expect(Array.isArray(payload?.targets)).toBe(true)
                    // Return configured label
                    return [
                        { model: "product.product", id: 42, label: "[SKU42] Test Product" },
                    ]
                },
                orm: {
                    call: async () => {
                        throw new Error("should not be called when RPC succeeds")
                    },
                },
            },
        }

        // Invoke patched method (runs async RPC inside)
        Message.prototype.prepareMessageBody.call({ env: fakeEnv }, container)
        await sleep(0)

        expect(a.textContent).toBe("[SKU42] Test Product")
        expect(a.getAttribute("data-oe-id")).toBe("42")
        expect(a.getAttribute("data-oe-model")).toBe("product.product")
    })

    test("renders icon when image_field provided", async () => {
        const container = document.createElement("div")
        const a = document.createElement("a")
        const href = "/web#id=77&model=product.product&view_type=form"
        a.setAttribute("href", href)
        a.textContent = href
        container.appendChild(a)

        const fakeEnv = {
            services: {
                rpc: async (route, payload) => {
                    expect(route).toBe("/discuss_record_links/labels")
                    return [{ model: "product.product", id: 77, label: "[SKU77] Iconic", image_field: "image_128" }]
                },
                orm: {
                    call: async () => {
                        throw new Error("no fallback")
                    }
                },
            },
        }

        Message.prototype.prepareMessageBody.call({ env: fakeEnv }, container)
        await sleep(0)

        const img = container.querySelector("img.o-drl-avatar")
        expect(img).toBeTruthy()
        expect(img.getAttribute("src")).toContain("/web/image/product.product/77/image_128")
        expect(container.querySelector('a').textContent.trim()).toBe("[SKU77] Iconic")
    })

    test("replaces http://localhost:8069/web#id=...&model=motor", async () => {
        const container = document.createElement("div")
        const a = document.createElement("a")
        const href = "http://localhost:8069/web#id=627&model=motor&view_type=form"
        a.setAttribute("href", href)
        a.textContent = href
        container.appendChild(a)

        const fakeEnv = {
            services: {
                rpc: async (route, payload) => {
                    expect(route).toBe("/discuss_record_links/labels")
                    expect(payload.targets[0]).toEqual({ model: "motor", id: 627 })
                    return [{ model: "motor", id: 627, label: "Yamaha F150 (2019)" }]
                },
                orm: {
                    call: async () => {
                        throw new Error("no fallback")
                    }
                },
            },
        }

        Message.prototype.prepareMessageBody.call({ env: fakeEnv }, container)
        await sleep(0)

        expect(a.textContent).toBe("Yamaha F150 (2019)")
        expect(a.getAttribute("data-oe-id")).toBe("627")
        expect(a.getAttribute("data-oe-model")).toBe("motor")
    })

    test("applies label for #fid param as well", async () => {
        const container = document.createElement("div")
        const a = document.createElement("a")
        const href = "http://localhost:8069/web#fid=101&model=product.product&view_type=form"
        a.setAttribute("href", href)
        a.textContent = href
        container.appendChild(a)

        const fakeEnv = {
            services: {
                rpc: async (route, payload) => {
                    expect(route).toBe("/discuss_record_links/labels")
                    // Should resolve fid→id
                    expect(payload.targets[0]).toEqual({ model: "product.product", id: 101 })
                    return [{ model: "product.product", id: 101, label: "[SKU101] Gadget" }]
                },
                orm: {
                    call: async () => {
                        throw new Error("no fallback")
                    }
                },
            },
        }

        Message.prototype.prepareMessageBody.call({ env: fakeEnv }, container)
        await sleep(0)

        expect(container.querySelector('a').textContent.trim()).toBe("[SKU101] Gadget")
    })

    test("falls back to display_name via ORM when RPC fails", async () => {
        const container = document.createElement("div")
        const a = document.createElement("a")
        a.setAttribute("href", "/web#id=7&model=product.product&view_type=form")
        a.textContent = a.getAttribute("href")
        container.appendChild(a)

        const fakeEnv = {
            services: {
                rpc: async () => {
                    throw new Error("RPC failure")
                },
                orm: {
                    call: async (model, method, args) => {
                        expect(model).toBe("product.product")
                        expect(method).toBe("read")
                        // args: [[ids], [fields]]
                        expect(Array.isArray(args?.[0])).toBe(true)
                        return [{ id: 7, display_name: "Fallback Name" }]
                    },
                },
            },
        }

        Message.prototype.prepareMessageBody.call({ env: fakeEnv }, container)
        await sleep(0)

        expect(a.textContent).toBe("Fallback Name")
        expect(a.getAttribute("data-oe-id")).toBe("7")
        expect(a.getAttribute("data-oe-model")).toBe("product.product")
    })

    test("linkifies bare internal URL text and applies label", async () => {
        const container = document.createElement("div")
        const href = "http://localhost:8069/web#id=99&model=product.product&view_type=form"
        // Insert as plain text (no anchor)
        container.textContent = `Please check ${href} ASAP`

        const fakeEnv = {
            services: {
                rpc: async (route, payload) => {
                    expect(route).toBe("/discuss_record_links/labels")
                    return [{ model: "product.product", id: 99, label: "[SKU99] Widget" }]
                },
                orm: {
                    call: async () => {
                        throw new Error("should not be called")
                    }
                },
            },
        }

        // Act
        Message.prototype.prepareMessageBody.call({ env: fakeEnv }, container)
        await sleep(0)

        // Assert: there is an anchor now and it is labeled
        const a = container.querySelector("a[href*='/web#']")
        expect(a).toBeTruthy()
        expect((a.textContent || '').trim()).toBe("[SKU99] Widget")
    })
})
