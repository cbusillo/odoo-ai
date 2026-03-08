import { browser } from "@web/core/browser/browser"

const permissionsApi = browser.navigator?.permissions

if (permissionsApi?.query) {
    const originalQuery = permissionsApi.query.bind(permissionsApi)

    permissionsApi.query = async (...args) => {
        const permissionResult = await originalQuery(...args)

        if (
            permissionResult &&
            typeof permissionResult.addEventListener !== "function" &&
            "onchange" in permissionResult
        ) {
            permissionResult.addEventListener = (eventName, listener) => {
                if (eventName !== "change") {
                    return
                }
                permissionResult.onchange = listener
            }

            permissionResult.removeEventListener = (eventName, listener) => {
                if (eventName !== "change") {
                    return
                }
                if (!listener || permissionResult.onchange === listener) {
                    permissionResult.onchange = null
                }
            }
        }

        return permissionResult
    }
}
