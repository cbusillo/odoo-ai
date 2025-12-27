/** @odoo-module */

/**
 * Tour test for multigraph view functionality
 * Following Odoo 18 patterns for tour tests
 */

import { registry } from "@web/core/registry";

// Product Processing Analytics: open, switch views, and assert basic UI health
registry.category("web_tour.tours").add("test_multigraph_view", {
    test: true,
    url: "/web#action=product_connect.action_product_processing_analytics&view_type=pivot",
    timeout: 60000,
    steps: () => [
        {
            content: "Wait for control panel",
            trigger: ".o_control_panel",
            timeout: 30000,
        },
        {
            content: "Breadcrumb present (analytics)",
            trigger: ".o_control_panel .o_breadcrumb",
            run() {
                const bc = document.querySelector(".o_control_panel .o_breadcrumb");
                const txt = (bc?.textContent || "").trim();
                if (!/(Processing|Analytics|Product)/i.test(txt)) {
                    throw new Error(`Unexpected breadcrumb: "${txt}"`);
                }
            },
        },
        {
            content: "Pivot view visible",
            trigger: ".o_view_controller .o_pivot",
            timeout: 30000,
        },
        {
            content: "Pivot has headers",
            trigger: ".o_view_controller .o_pivot table th",
        },
        {
            content: "Switch to Multigraph view",
            trigger:
                "button.o_switch_view.o_multigraph:visible, .o_control_panel .o_switch_view .o_multigraph:visible",
            timeout: 30000,
            run() {
                (document.querySelector("button.o_switch_view.o_multigraph")
                    || document.querySelector(".o_control_panel .o_switch_view .o_multigraph"))?.click();
            },
        },
        {
            content: "Graph view visible",
            trigger: ".o_view_controller .o_graph_view",
            timeout: 30000,
        },
        {
            content: "Multigraph renderer is present",
            trigger: ".o_multigraph_renderer",
            timeout: 30000,
        },
        {
            content: "Renderer has canvas or no-data message",
            // Accept either rendered chart or empty state, to avoid flakiness with default filters
            trigger:
                ".o_multigraph_renderer .o_graph_canvas_container canvas, .o_multigraph_renderer .o_graph_no_data",
            timeout: 30000,
        },
        {
            content: "Switch back to Pivot",
            trigger: "button.o_switch_view.o_pivot:visible, .o_control_panel .o_switch_view .o_pivot:visible",
            run() {
                (document.querySelector("button.o_switch_view.o_pivot")
                    || document.querySelector(".o_control_panel .o_switch_view .o_pivot"))?.click();
            },
        },
        {
            content: "Pivot visible again",
            trigger: ".o_view_controller .o_pivot",
            timeout: 30000,
        },
        {
            content: "Search bar available",
            trigger: ".o_control_panel .o_searchview input",
        },
        {
            trigger: "body",
            content: "Finish",
            run() {
                console.log("tour succeeded");
            },
        },
    ],
});
