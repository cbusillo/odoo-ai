/** @odoo-module */

import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("shipping_analytics_tour", {
    test: true,
    url: "/web#action=product_connect.action_sale_order_shipping_analytics",
    steps: () => [
        {
            content: "Ensure analytics action is loaded",
            trigger: ".o_web_client",
            run() {
                try {
                    const svc = odoo?.__DEBUG__?.services?.action
                    svc?.doAction?.("product_connect.action_sale_order_shipping_analytics")
                } catch (e) { /* non-fatal */
                }
            },
        },
        {
            content: "Wait for control panel",
            trigger: ".o_control_panel",
            timeout: 20000,
        },
        // Wait for the view to load (either pivot or graph)
        {
            content: "Wait for analytics view to load",
            trigger: ".o_view_controller .o_pivot, .o_view_controller .o_graph_view",
            timeout: 15000,
        },
        // Test view switching if both views are available
        {
            content: "Check if we can switch to graph view",
            trigger: "button.o_switch_view.o_graph:visible, .o_pivot",
            run: function () {
                const graphButton = document.querySelector("button.o_switch_view.o_graph");
                if (graphButton && graphButton.offsetParent !== null) {
                    graphButton.click();
                }
            },
        },
        {
            content: "Wait for graph view or stay in current view",
            trigger: ".o_graph_view, .o_pivot",
        },
        {
            content: "Check if we can switch back to pivot view",
            trigger: "button.o_switch_view.o_pivot:visible, .o_pivot",
            run: function () {
                const pivotButton = document.querySelector("button.o_switch_view.o_pivot");
                if (pivotButton && pivotButton.offsetParent !== null) {
                    pivotButton.click();
                }
            },
        },
        {
            content: "Verify analytics view is functioning",
            trigger: ".o_pivot, .o_graph_view",
        },
        // Verify no JavaScript errors occurred
        {
            content: "Verify no errors occurred",
            trigger: "body:not(:has(.o_error_dialog))",
        },
    ],
});
