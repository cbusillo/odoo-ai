import { onWillDestroy } from "@odoo/owl"
import { browser } from "@web/core/browser/browser"
import { patch } from "@web/core/utils/patch"
import { WebClient } from "@web/webclient/webclient"

export function observeNotificationPermissionChanges(permissionStatus, onPermissionChange) {
    if (!permissionStatus || typeof onPermissionChange !== "function") {
        return () => {
        }
    }

    if (typeof permissionStatus.addEventListener === "function") {
        permissionStatus.addEventListener("change", onPermissionChange)
        return () => permissionStatus.removeEventListener?.("change", onPermissionChange)
    }

    if (!("onchange" in permissionStatus)) {
        return () => {
        }
    }

    const previousOnchange = permissionStatus.onchange
    const wrappedOnchange = (event) => {
        if (typeof previousOnchange === "function") {
            previousOnchange.call(permissionStatus, event)
        }
        onPermissionChange(event)
    }

    try {
        permissionStatus.onchange = wrappedOnchange
    } catch {
        return () => {
        }
    }

    return () => {
        try {
            if (permissionStatus.onchange === wrappedOnchange) {
                permissionStatus.onchange = previousOnchange ?? null
            }
        } catch {
            // Some browser PermissionStatus implementations expose readonly members.
        }
    }
}

export async function registerNotificationPermissionObserver(
    permissionQueryPromise,
    onPermissionChange,
    wasDestroyed = () => false
) {
    try {
        const permissionStatus = await permissionQueryPromise
        if (wasDestroyed()) {
            return () => {
            }
        }
        const removeObserver = observeNotificationPermissionChanges(
            permissionStatus,
            onPermissionChange
        )
        if (wasDestroyed()) {
            removeObserver()
            return () => {
            }
        }
        return removeObserver
    } catch {
        return () => {
        }
    }
}

// noinspection JSUnusedGlobalSymbols
patch(WebClient.prototype, {
    setup() {
        const originalNavigator = browser.navigator
        browser.navigator = { ...originalNavigator, permissions: undefined }
        try {
            super.setup()
        } finally {
            browser.navigator = originalNavigator
        }

        const permissionsApi = browser.navigator?.permissions
        if (!permissionsApi?.query) {
            return
        }

        let removePermissionObserver = () => {
        }
        let destroyed = false
        const onPermissionChange = () => {
            if (this._canSendNativeNotification) {
                this._subscribePush()
            } else {
                this._unsubscribePush()
            }
        }

        registerNotificationPermissionObserver(
            permissionsApi.query({ name: "notifications" }),
            onPermissionChange,
            () => destroyed
        ).then((cleanup) => {
            if (destroyed) {
                cleanup()
                return
            }
            removePermissionObserver = cleanup
        })

        onWillDestroy(() => {
            destroyed = true
            removePermissionObserver()
        })
    }
})
