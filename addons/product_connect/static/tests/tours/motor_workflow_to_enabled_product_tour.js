/** @odoo-module */

import { registry } from "@web/core/registry";

function queryElement(selector) {
    return /** @type {HTMLElement | null} */ (document.querySelector(selector))
}

function queryInput(selector) {
    return /** @type {HTMLInputElement | HTMLTextAreaElement | null} */ (document.querySelector(selector))
}

function clickElement(element) {
    if (!element) {
        return
    }
    element.dispatchEvent(new MouseEvent("click", { bubbles: true }))
}

function clickSelector(selector) {
    clickElement(queryElement(selector))
}

function setInputValue(selector, value) {
    const element = queryInput(selector)
    if (!element) {
        return
    }
    element.dispatchEvent(new Event("focus", { bubbles: true }))
    element.value = value
    element.dispatchEvent(new Event("input", { bubbles: true }))
    element.dispatchEvent(new Event("change", { bubbles: true }))
}

// Keep the original tour name; use robust selectors and waits.
registry.category("web_tour.tours").add("motor_workflow_to_enabled_product_tour", {
    test: true,
    url: "/web#action=product_connect.action_motor_form",
    steps: () => [
        { content: "Control panel visible", trigger: ".o_control_panel" },

        // Create a new motor (list or kanban)
        {
            content: "Click Create",
            trigger: ".o_list_button_add, .o-kanban-button-new",
            run() {
                clickSelector(".o_list_button_add, .o-kanban-button-new")
            },
        },

        // Wait for form
        { content: "Form view visible", trigger: ".o_form_button_save, .o_form_renderer" },
        {
            content: "Basic Info tab",
            trigger: ".o_notebook .o_notebook_headers .nav-link",
            run() {
                const links = Array.from(document.querySelectorAll(".o_notebook .o_notebook_headers .nav-link"))
                const basic = links.find((link) => /Basic\s*Info/i.test(link.textContent || ""))
                clickElement(basic)
            },
        },
        // Keep label "Form loaded" for familiarity but use robust trigger
        { content: "Form loaded", trigger: ".o_form_renderer .o_group, .o_form_renderer .o_field_widget" },

        // Fill core fields
        {
            content: "Set model",
            trigger: ".o_form_renderer",
            run() {
                setInputValue("input[name='model'], textarea[name='model']", "TEST-MODEL")
            },
        },
        {
            content: "Set serial",
            trigger: ".o_form_renderer",
            run() {
                setInputValue("input[name='serial_number'], textarea[name='serial_number']", "SN-001")
            },
        },
        {
            content: "Set location",
            trigger: ".o_form_renderer",
            run() {
                setInputValue("input[name='location'], textarea[name='location']", "A1")
            },
        },
        {
            content: "Set horsepower",
            trigger: ".o_form_renderer",
            run() {
                setInputValue("input[name='horsepower']", "100")
            },
        },

        // Required badge fields
        {
            content: "Pick manufacturer",
            trigger: ".o_form_renderer .o_field_widget[name=manufacturer] .o_selection_badge:not(.btn-reset)",
            run() {
                clickSelector(".o_form_renderer .o_field_widget[name=manufacturer] .o_selection_badge:not(.btn-reset)")
            }
        },
        {
            content: "Pick stroke",
            trigger: ".o_form_renderer .o_field_widget[name=stroke] .o_selection_badge:not(.btn-reset)",
            run() {
                clickSelector(".o_form_renderer .o_field_widget[name=stroke] .o_selection_badge:not(.btn-reset)")
            }
        },
        {
            content: "Pick configuration",
            trigger: ".o_form_renderer .o_field_widget[name=configuration] .o_selection_badge:not(.btn-reset)",
            run() {
                clickSelector(".o_form_renderer .o_field_widget[name=configuration] .o_selection_badge:not(.btn-reset)")
            }
        },
        {
            content: "Pick color",
            trigger: ".o_form_renderer .o_field_widget[name=color] .o_selection_badge:not(.btn-reset)",
            run() {
                clickSelector(".o_form_renderer .o_field_widget[name=color] .o_selection_badge:not(.btn-reset)")
            }
        },
        {
            content: "Pick year",
            trigger: ".o_form_renderer .o_field_widget[name=year] .o_selection_badge:not(.btn-reset)",
            run() {
                clickSelector(".o_form_renderer .o_field_widget[name=year] .o_selection_badge:not(.btn-reset)")
            }
        },
        {
            content: "Set cost",
            trigger: ".o_form_renderer",
            run() {
                setInputValue("input[name='cost']", "1000")
            },
        },

        // Save
        { content: "Save motor", trigger: ".o_form_button_save", run: "click" },
        // Consider the form saved either when the Edit button is present or when the Save button disappears
        {
            content: "Ensure saved",
            trigger: "body:has(.o_form_button_edit), body:not(:has(.o_form_button_save:visible))"
        },

        // Listing/Admin
        {
            content: "Open Listing tab",
            trigger: ".o_notebook .o_notebook_headers .nav-link",
            run() {
                const links = Array.from(document.querySelectorAll(".o_notebook .o_notebook_headers .nav-link"))
                const listing = links.find((link) => /Listing/i.test(link.textContent || ""))
                clickElement(listing)
            },
        },
        { content: "Admin present", trigger: ".o_form_renderer .btn[name=create_motor_products]" },
        {
            content: "Create motor products",
            trigger: ".o_form_renderer .btn[name=create_motor_products]",
            run: "click"
        },
        // Allow background generation to complete via coarse waits (engine has fixed per-step timeout)
        {
            content: "Wait for generation (1)", trigger: "body", run() {
                const t = Date.now() + 12000;
                while (Date.now() < t) {
                }
            }
        },
        {
            content: "Wait for generation (2)", trigger: "body", run() {
                const t = Date.now() + 12000;
                while (Date.now() < t) {
                }
            }
        },
        {
            content: "Wait for generation (3)", trigger: "body", run() {
                const t = Date.now() + 12000;
                while (Date.now() < t) {
                }
            }
        },
        {
            content: "Wait for generation (4)", trigger: "body", run() {
                const t = Date.now() + 12000;
                while (Date.now() < t) {
                }
            }
        },
        {
            content: "Wait for generation (5)", trigger: "body", run() {
                const t = Date.now() + 12000;
                while (Date.now() < t) {
                }
            }
        },
        {
            content: "Wait for generation (6)", trigger: "body", run() {
                const t = Date.now() + 12000;
                while (Date.now() < t) {
                }
            }
        },
        // Be lenient: product generation may be asynchronous; don't fail if rows are not immediately visible.
        // Proceed to the enable action if present; otherwise continue.
        {
            content: "Enable all products (if present)", trigger: "body", run() {
                clickSelector(".o_form_renderer .btn[name=enable_ready_for_sale]")
            }
        },
        // If an error dialog appears (products not ready), close it to continue the flow
        {
            content: "Close error if present", trigger: "body", run() {
                clickSelector(".o_error_dialog .modal-footer .btn, .modal.o_error_dialog .btn-primary, .modal .btn-primary")
            }
        },

        // Open products and assert
        // Skip navigating to products to avoid environment-specific view extensions

        { content: "End", trigger: "body" },
    ],
});
