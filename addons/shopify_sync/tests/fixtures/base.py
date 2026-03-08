from test_support.tests.fixtures.base_cases import (
    SharedIntegrationTestCase,
    SharedTourTestCase,
    SharedUnitTestCase,
)

from ..common_imports import common


@common.tagged(*common.UNIT_TAGS)
class UnitTestCase(SharedUnitTestCase):
    pass


@common.tagged(*common.INTEGRATION_TAGS)
class IntegrationTestCase(SharedIntegrationTestCase):
    pass


@common.tagged(*common.TOUR_TAGS)
class TourTestCase(SharedTourTestCase):
    pass
