import { ListController } from "@web/views/list/list_controller"
import { listView } from "@web/views/list/list_view"
import { registry } from "@web/core/registry"
import { useService } from "@web/core/utils/hooks"
import { onWillUnmount } from "@odoo/owl"

class AutoRefreshListController extends ListController {
    static services = ["action"]

    setup() {
        super.setup()
        this.action = useService("action")
        this._reloading = false
        const context = /** @type {{ refreshInterval?: number }} */ (this.props?.context || {})
        const seconds = Number(context.refreshInterval || 10)
        if (seconds > 0) {
            this._interval = setInterval(() => this._softReload(), seconds * 1_000)
            onWillUnmount(() => clearInterval(this._interval))
        }
        this.action = useService("action")
    }


    async _softReload() {
        if (this._reloading) return
        this._reloading = true
        try {
            await this.model.load({ reload: true })
        } catch {
            await this.action.doAction({ type: "ir.actions.client", tag: "soft_reload" })
        } finally {
            this._reloading = false
        }
    }
}

registry.category("views").add("list_autorefresh", {
    ...listView,
    Controller: AutoRefreshListController,
})
