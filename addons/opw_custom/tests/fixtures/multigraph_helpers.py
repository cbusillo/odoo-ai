from typing import Any


def load_multigraph_action_context(
    test_case: Any,
    *,
    required_view_mode: str,
) -> tuple[Any, Any, list[Any]]:
    action = test_case.env.ref("opw_custom.action_product_processing_analytics", raise_if_not_found=False)
    action = action.exists() if action else test_case.env["ir.actions.act_window"]
    test_case.assertTrue(action, "Multigraph action should exist")
    test_case.assertEqual(action.res_model, "product.template")
    test_case.assertIn(required_view_mode, action.view_mode)

    model = test_case.env[action.res_model]
    test_case.assertTrue(hasattr(model, "search"), "Should be able to access product.template model")

    domain = eval(action.domain) if action.domain else []
    try:
        model.search(domain, limit=1)
    except Exception as search_error:
        test_case.fail(f"Domain search failed: {search_error}")

    return action, model, domain
