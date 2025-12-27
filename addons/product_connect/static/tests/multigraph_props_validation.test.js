/** @odoo-module */
import { test, expect } from "@odoo/hoot"
import { multigraphView } from "@product_connect/views/multigraph/multigraph_view"
import { MultigraphModel } from "@product_connect/views/multigraph/multigraph_model"
import { MultigraphRenderer } from "@product_connect/views/multigraph/multigraph_renderer"

test("@product_connect multigraph view props function returns valid props structure", () => {
    const mockGenericProps = {
        arch: new DOMParser().parseFromString('<graph/>', 'text/xml').documentElement,
        fields: {
            name: { string: "Name", type: "char" },
            value: { string: "Value", type: "float" }
        }
    }

    const mockView = {
        type: "multigraph"
    }

    const props = multigraphView.props(mockGenericProps, mockView)

    // Validate key props exist and have correct types (avoid asserting internal view defaults)
    expect(props).not.toBe(undefined)
    expect(props.Model).toBe(MultigraphModel)
    expect(props.Renderer).toBe(MultigraphRenderer)
    expect(typeof props.modelParams).toBe("object")
})

test("@product_connect multigraph view props handles undefined gracefully", () => {
    const mockGenericProps = {
        arch: new DOMParser().parseFromString('<graph/>', 'text/xml').documentElement,
        fields: {}
    }

    const mockView = {
        type: "multigraph"
    }

    // Should not throw an error even with minimal props
    const props = multigraphView.props(mockGenericProps, mockView)

    expect(props).not.toBe(undefined)
    expect(props.modelParams).not.toBe(undefined)
})
