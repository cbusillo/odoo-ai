from ..common_imports import tagged, TOUR_TAGS
from ..fixtures.base import TourTestCase


@tagged(*TOUR_TAGS, "product_connect")
class TestMotorWorkflowTour(TourTestCase):
    def test_motor_workflow_to_enabled_product_tour(self) -> None:
        # Land directly on the Motor action so the tour can find the control panel
        self.start_tour("/web#action=product_connect.action_motor_form", "motor_workflow_to_enabled_product_tour")
