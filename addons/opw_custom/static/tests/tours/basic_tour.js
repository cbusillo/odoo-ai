/** @odoo-module */

import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("test_basic_tour", {
    test: true,
    url: "/web",
    timeout: 60000, // 60 seconds timeout
    steps: () => [
        {
            content: "Wait for Odoo to load",
            trigger: ".o_web_client",
            timeout: 20000, // 20 seconds for initial load
        },
        {
            content: "Verify Odoo loaded successfully",
            trigger: "body:not(.o_error_dialog)",
            run: function() {
                // Check that no error dialog is present
                const errorDialog = document.querySelector(".o_error_dialog");
                if (errorDialog) {
                    throw new Error("Error dialog found when none expected");
                }
                console.log("Basic tour completed successfully - Odoo loaded without errors");
            },
            timeout: 5000,
        },
    ],
});
