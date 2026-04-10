import { describe, expect, test, vi } from "@odoo/hoot"

import {
    observeNotificationPermissionChanges,
    registerNotificationPermissionObserver,
} from "@environment_overrides/js/notification_permission_patch"

describe("@environment_overrides notification permission patch", () => {
    test("uses native event listeners when available", () => {
        const addEventListener = vi.fn()
        const removeEventListener = vi.fn()
        const permissionStatus = {
            addEventListener,
            removeEventListener,
        }
        const onPermissionChange = vi.fn()

        const cleanup = observeNotificationPermissionChanges(permissionStatus, onPermissionChange)

        expect(addEventListener).toHaveBeenCalledWith("change", onPermissionChange)
        cleanup()
        expect(removeEventListener).toHaveBeenCalledWith("change", onPermissionChange)
    })

    test("falls back to onchange when event listeners are unavailable", () => {
        const previousOnchange = vi.fn()
        const permissionStatus = {
            addEventListener: undefined,
            onchange: previousOnchange,
        }
        const onPermissionChange = vi.fn()

        const cleanup = observeNotificationPermissionChanges(permissionStatus, onPermissionChange)
        permissionStatus.onchange({ type: "change" })

        expect(previousOnchange).toHaveBeenCalledTimes(1)
        expect(onPermissionChange).toHaveBeenCalledTimes(1)

        cleanup()
        expect(permissionStatus.onchange).toBe(previousOnchange)
    })

    test("degrades gracefully when onchange is readonly", () => {
        const permissionStatus = {}
        Object.defineProperty(permissionStatus, "addEventListener", {
            configurable: false,
            enumerable: true,
            value: undefined,
            writable: false,
        })
        Object.defineProperty(permissionStatus, "onchange", {
            configurable: true,
            enumerable: true,
            get() {
                return null
            },
            set() {
                throw new TypeError("Attempted to assign to readonly property.")
            },
        })

        const cleanup = observeNotificationPermissionChanges(permissionStatus, vi.fn())

        expect(() => cleanup()).not.toThrow()
    })

    test("does not attach an observer after teardown", async () => {
        const addEventListener = vi.fn()
        const permissionStatus = {
            addEventListener,
            removeEventListener: vi.fn(),
        }

        const cleanup = await registerNotificationPermissionObserver(
            Promise.resolve(permissionStatus),
            vi.fn(),
            () => true
        )

        expect(addEventListener).not.toHaveBeenCalled()
        expect(() => cleanup()).not.toThrow()
    })
})
