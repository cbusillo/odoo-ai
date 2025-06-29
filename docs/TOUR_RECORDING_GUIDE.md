# Tour Recording Guide for Test Generation

## Overview

This guide explains how to leverage Odoo's built-in tour recording feature to quickly generate test cases. Tour
recording captures user interactions that can be converted into automated tests.

## Recording Tours in Odoo 18

### 1. Enable Tour Recording

1. **Enable Debug Mode**: Add `?debug=1` to your URL (e.g., `http://localhost:8069/web?debug=1`)
2. **Access Tour Recorder**:
    - Click the bug icon in the top menu bar
    - Select "Start Tour" or "Record a new tour"
    - Give your tour a meaningful name (e.g., `motor_creation_workflow`)

### 2. Perform Your Workflow

- Execute the exact steps you want to test
- The recorder captures all clicks, inputs, and navigation
- Be deliberate with your actions - every click is recorded

### 3. Stop Recording

- Click the stop button when complete
- The tour is saved in the database (`web_tour.tour` model)

## Converting Recorded Tours to Test Tours

### Problems with Raw Recordings

Recorded tours often use brittle selectors:

```javascript
// ❌ Bad - Position-dependent, will break if options change
trigger: ".o_selection_badge:nth-child(19)"  // What is this?
trigger: ".o_input:nth-child(2)"            // Which input?

// ✅ Good - Semantic selectors that won't break
trigger: ".o_field_widget[name='year'] .o_selection_badge:contains('2024')"
trigger: ".o_field_widget[name='serial_number'] input"
```

### Conversion Process

1. **Extract the recorded tour** from the database
2. **Analyze nth-child selectors** to determine actual values
3. **Replace with semantic selectors** that are maintenance-friendly
4. **Add validation steps** to ensure actions succeeded
5. **Add test isolation** (unique values for concurrent testing)

## Best Practices for Tour Tests

### 1. Structure Your Test File

```javascript
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("your_workflow_tour", {
    test: true,  // Mark as test tour
    steps: () => [
        // Steps here
    ],
});
```

### 2. Add Validation Steps

Don't just click through - verify results:

```javascript
const validationStep = {
    content: "Verify motor was created successfully",
    trigger: ".o_form_view.o_form_saved",
    run: function () {
        // Validate critical fields
        const manufacturer = document.querySelector(".o_field_widget[name='manufacturer'] .o_field_many2one_selection");
        if (!manufacturer || !manufacturer.textContent.includes("Mercury")) {
            throw new Error("Manufacturer was not saved correctly");
        }

        const horsepower = document.querySelector(".o_field_widget[name='horsepower'] input");
        if (!horsepower || horsepower.value !== "150") {
            throw new Error("Horsepower was not saved correctly");
        }

        console.log("✓ Motor created with correct values");
    }
};
```

### 3. Use Test Isolation

Generate unique values to allow parallel test execution:

```javascript
const serialNumberStep = {
    content: "Enter serial number",
    trigger: ".o_field_widget[name='serial_number'] input",
    run: function () {
        // Generate unique serial for test isolation
        const serial = "TEST-" + Date.now();
        const input = document.querySelector(".o_field_widget[name='serial_number'] input");
        input.value = serial;
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }
};
```

### 4. Improve Selectors

```javascript
// Helper function for better selectors
function selectFieldOption(fieldName, value) {
    return {
        content: `Select ${value} in ${fieldName} field`,
        trigger: `.o_field_widget[name='${fieldName}'] .o_selection_badge:contains('${value}')`,
        run: "click"
    };
}

// Usage
const steps = [
    selectFieldOption("year", "2024"),
    selectFieldOption("stroke", "4 Stroke")
];
```

## Workflow for Future Implementation

### 1. Recording Phase

1. **Plan your test scenario** - Know what you're testing before recording
2. **Record the happy path** - Get the basic flow working
3. **Note any dynamic data** - Serial numbers, dates, etc.

### 2. Conversion Phase

1. **Export the recorded tour**:

```python
# In Odoo shell
tour = env['web_tour.tour'].search([('name', '=', 'your_tour_name')])
for step in tour.step_ids:
    print(f"Trigger: {step.trigger}")
    print(f"Run: {step.run}")
```

- **Identify brittle selectors** and research actual values:

```python
# Find what nth-child(N) actually selects
years = env['motor']._fields['year'].selection(env['motor'])
print(f"Year option 19: {years[18]}")  # 0-indexed
```

- **Create test file** with improved selectors

### 3. Enhancement Phase

Add these critical elements:

1. **Wait conditions**:

```javascript
const waitStep = {
    content: "Wait for form to fully load",
    trigger: ".o_form_view:not(.o_form_loading)"
};
```

- **Error handling**:

```javascript
const errorCheckStep = {
    content: "Verify no errors occurred",
    trigger: "body:not(:has(.o_notification_error))"
};
```

- **Data verification**:

```javascript
const verifyProductsStep = {
    content: "Verify products were created",
    trigger: ".o_data_row",
    run: function () {
        const rowCount = document.querySelectorAll(".o_data_row").length;
        if (rowCount === 0) {
            throw new Error("No products were created!");
        }
        console.log(`✓ Created ${rowCount} products`);
    }
};
```

## Validation Requirements

Every tour test should validate:

1. **Initial state** - Correct starting point
2. **Action success** - Each action completed without errors
3. **Data integrity** - Values saved correctly
4. **Final state** - Expected end result achieved
5. **No side effects** - No unexpected errors or warnings

## Example: Complete Test Conversion

### Recorded (Raw):

```javascript
const rawStep = {
    trigger: ".o_selection_badge:nth-child(19)",
    run: "click"
};
```

### Converted (Maintainable):

```javascript
const improvedStep = {
    content: "Select year 2024",
    trigger: ".o_field_widget[name='year'] .o_selection_badge:contains('2024')",
    run: "click",
    // Optional: Add validation
    extra_trigger: ".o_field_widget[name='year'] .o_field_many2one_selection:contains('2024')"
};
```

## Automation Script

Consider creating a conversion script:

```python
# tour_converter.py
def convert_tour_to_test(tour_name):
    """Convert recorded tour to maintainable test"""
    tour = env['web_tour.tour'].search([('name', '=', tour_name)])

    # Analyze selectors
    for step in tour.step_ids:
        if ":nth-child(" in step.trigger:
            # Extract and convert to semantic selector
            field_name = extract_field_name(step.trigger)
            value = infer_nth_child_value(step.trigger)
            better_selector = f".o_field_widget[name='{field_name}']:contains('{value}')"

    # Generate test file
    generate_test_file(converted_steps)
```

## Benefits

1. **Rapid test creation** - Record once, refine to perfection
2. **Accurate user flows** - Captures real user behavior
3. **Easy updates** - Re-record when UI changes significantly
4. **Better coverage** - Non-developers can contribute test scenarios

## Limitations

1. **Selector brittleness** - Requires post-processing
2. **No assertions** - Must add validation manually
3. **Linear flows only** - Can't handle complex branching
4. **Timing issues** - May need additional wait conditions

## Conclusion

Tour recording is an excellent starting point for test creation. The key is to:

1. Record the interaction
2. Convert to maintainable selectors
3. Add comprehensive validations
4. Ensure test isolation

This hybrid approach combines the speed of recording with the reliability of well-crafted tests.