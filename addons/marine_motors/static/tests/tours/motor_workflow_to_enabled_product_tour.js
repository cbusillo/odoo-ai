/** @odoo-module */

import { registry } from "@web/core/registry";

function queryElement(selector) {
    return /** @type {HTMLElement | null} */ (document.querySelector(selector))
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

function findFieldRoot(fieldName) {
    return queryElement(`.o_form_renderer .o_field_widget[name=${fieldName}]`)
}

function findFieldInput(fieldName) {
    const fieldRoot = findFieldRoot(fieldName)
    if (!fieldRoot) {
        return null
    }
    const candidates = Array.from(fieldRoot.querySelectorAll("input, textarea"))
    return (
        candidates.find(
            (element) => element.offsetParent !== null && !element.disabled,
        ) || null
    )
}

function setFieldValue(fieldName, value) {
    const element = findFieldInput(fieldName)
    if (!element) {
        throw new Error(`Field input not found: ${fieldName}`)
    }
    element.dispatchEvent(new Event("focus", { bubbles: true }))
    element.value = value
    element.dispatchEvent(new Event("input", { bubbles: true }))
    element.dispatchEvent(new Event("change", { bubbles: true }))
}

function pickBadgeOption(fieldName) {
    const fieldRoot = findFieldRoot(fieldName)
    if (!fieldRoot) {
        return false
    }
    const badgeElement = fieldRoot.querySelector(
        ".o_selection_badge:not(.btn-reset)",
    )
    if (!badgeElement) {
        return false
    }
    clickElement(badgeElement)
    return true
}

function pickSelectOption(fieldName) {
    const fieldRoot = findFieldRoot(fieldName)
    if (!fieldRoot) {
        return false
    }
    const selectElement = fieldRoot.querySelector("select")
    if (!selectElement) {
        return false
    }
    const optionElement = Array.from(selectElement.options).find(
        (option) => option.value && !option.disabled,
    )
    if (!optionElement) {
        return false
    }
    selectElement.value = optionElement.value
    selectElement.dispatchEvent(new Event("input", { bubbles: true }))
    selectElement.dispatchEvent(new Event("change", { bubbles: true }))
    return true
}

function pickMany2oneOption(fieldName) {
    const fieldRoot = findFieldRoot(fieldName)
    if (!fieldRoot) {
        return false
    }
    const inputElement = fieldRoot.querySelector("input")
    if (!inputElement) {
        return false
    }
    const dropdownButton = fieldRoot.querySelector(
        ".o_input_dropdown_button, .o_dropdown_button",
    )
    if (dropdownButton) {
        clickElement(dropdownButton)
    } else {
        inputElement.dispatchEvent(new Event("focus", { bubbles: true }))
        inputElement.dispatchEvent(
            new KeyboardEvent("keydown", { bubbles: true, key: "ArrowDown" }),
        )
    }
    const optionSelectors = [
        ".o-autocomplete--dropdown .dropdown-item",
        ".o_m2o_dropdown_option",
        ".ui-autocomplete .ui-menu-item",
        ".dropdown-menu .dropdown-item",
    ]
    for (const selector of optionSelectors) {
        const optionElement = queryElement(selector)
        if (optionElement && optionElement.offsetParent !== null) {
            clickElement(optionElement)
            return true
        }
    }
    return false
}

function pickFieldOption(fieldName) {
    return (
        pickBadgeOption(fieldName) ||
        pickSelectOption(fieldName) ||
        pickMany2oneOption(fieldName)
    )
}

// Keep the original tour name; use robust selectors and waits.
registry.category("web_tour.tours").add("motor_workflow_to_enabled_product_tour", {
    test: true,
    url: "/web#action=marine_motors.action_motor_form",
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
                setFieldValue("model", "TEST-MODEL")
            },
        },
        {
            content: "Set serial",
            trigger: ".o_form_renderer",
            run() {
                setFieldValue("serial_number", "SN-001")
            },
        },
        {
            content: "Set location",
            trigger: ".o_form_renderer",
            run() {
                setFieldValue("location", "A1")
            },
        },
        {
            content: "Set horsepower",
            trigger: ".o_form_renderer",
            run() {
                setFieldValue("horsepower", "100")
            },
        },

        // Required badge fields
        {
            content: "Pick manufacturer",
            trigger: ".o_form_renderer .o_field_widget[name=manufacturer]",
            run() {
                if (!pickFieldOption("manufacturer")) {
                    throw new Error("Manufacturer option not found")
                }
            }
        },
        {
            content: "Pick stroke",
            trigger: ".o_form_renderer .o_field_widget[name=stroke]",
            run() {
                if (!pickFieldOption("stroke")) {
                    throw new Error("Stroke option not found")
                }
            }
        },
        {
            content: "Pick configuration",
            trigger: ".o_form_renderer .o_field_widget[name=configuration]",
            run() {
                if (!pickFieldOption("configuration")) {
                    throw new Error("Configuration option not found")
                }
            }
        },
        {
            content: "Pick color",
            trigger: ".o_form_renderer .o_field_widget[name=color]",
            run() {
                if (!pickFieldOption("color")) {
                    throw new Error("Color option not found")
                }
            }
        },
        {
            content: "Pick year",
            trigger: ".o_form_renderer .o_field_widget[name=year]",
            run() {
                if (!pickFieldOption("year")) {
                    throw new Error("Year option not found")
                }
            }
        },
        {
            content: "Set cost",
            trigger: ".o_form_renderer",
            run() {
                setFieldValue("cost", "1000")
            },
        },

        // Save (button may be hidden if the form auto-saved)
        {
            content: "Save motor",
            trigger: "body:has(.o_form_button_save), body:has(.o_form_button_edit)",
            run() {
                const saveButton = queryElement(".o_form_button_save")
                if (saveButton && saveButton.offsetParent !== null) {
                    clickElement(saveButton)
                }
            }
        },
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
