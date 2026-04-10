/** @odoo-module */

import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("smoke_login_tour", {
    test: true,
    url: "/web",
    steps: () => [
        {
            content: "Load the web client shell",
            trigger: ".o_web_client",
        },
        {
            content: "Ensure the apps menu is visible",
            trigger: ".o_app[data-menu-xmlid]",
        },
        {
            content: "Confirm the user menu renders",
            trigger: ".o_user_menu",
        },
    ],
});

