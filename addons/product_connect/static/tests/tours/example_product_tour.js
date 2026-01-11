/** @odoo-module */

import { registry } from "@web/core/registry";

/**
 * Example tour test for Product Connect module
 * This tour demonstrates navigating to the Product Connect app and performing basic actions
 */
registry.category("web_tour.tours").add("example_product_tour", {
    test: true,
    // Use the simpler list-edit action to avoid enterprise-only fields in stock tree view
    url: "/web#action=product_connect.action_product_template_list_edit",
    steps: () => [
        {
            content: "Wait for web client to be ready",
            trigger: ".o_web_client",
        },
        {
            content: "Wait for control panel (action loaded)",
            trigger: ".o_control_panel",
            timeout: 20000,
            run() {
                const bc = document.querySelector(".o_breadcrumb")
                if (!bc || !/Product/i.test(bc.textContent || "")) {
                    // As a fallback, force-load the action again
                    try {
                        const actionService = window.odoo?.["__DEBUG__"]?.services?.action
                        actionService?.doAction?.("product_connect.action_product_template_list_edit")
                    } catch (e) {
                    }
                }
            },
        },
        {
            content: "Confirm breadcrumb exists",
            trigger: ".o_breadcrumb",
            run() {
                const bc = document.querySelector(".o_breadcrumb")
                console.log("Breadcrumb:", bc && bc.textContent)
            },
        },
        {
            content: "Tour finished",
            trigger: "body",
            run() {
                console.log("example_product_tour finished")
            },
        },
    ],
});
