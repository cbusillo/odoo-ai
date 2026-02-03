"""Example Product Tour Test

This module demonstrates how to create a tour test for the OPW Custom module.
Tour tests are browser-based tests that simulate user interactions.
"""

from ..common_imports import tagged, TOUR_TAGS
from ..fixtures.base import TourTestCase


@tagged(*TOUR_TAGS, "opw_custom")
class TestExampleProductTour(TourTestCase):
    """Test class for the example product tour.

    This test will:
    1. Load the Odoo web client
    2. Navigate to the OPW Custom app
    3. Verify the app loads without errors
    4. Check that basic navigation works
    """

    def test_example_product_tour(self) -> None:
        """Run the example product tour test.

        This test starts at the /web URL and runs through the
        'example_product_tour' tour defined in the JavaScript file.
        """
        # Use the fixed start_tour method with proper completion detection
        self.start_tour(
            "/web#action=opw_custom.action_product_template_list_edit", "example_product_tour", login=self._get_test_login()
        )

    def test_product_navigation(self) -> None:
        """Test navigating through product views.

        This is another example showing you can have multiple test methods.
        """
        # You could create another tour or reuse the same one with different parameters
        self.start_tour(
            "/web#action=opw_custom.action_product_template_list_edit", "example_product_tour", login=self._get_test_login()
        )
