from ...models.external_id_mixin import ExternalIdMixin
from ..common_imports import common
from ..fixtures.base import UnitTestCase


class FakeExternalIdsUiModel:
    _name = "external.id.fixture"
    _external_ids_auto_ui = True
    _fields = {"external_ids": object()}
    _inject_external_ids_button = ExternalIdMixin.__dict__["_inject_external_ids_button"]
    _inject_external_ids_page = ExternalIdMixin.__dict__["_inject_external_ids_page"]
    _build_external_ids_page_arch = ExternalIdMixin.__dict__["_build_external_ids_page_arch"]
    _inject_external_ids_form_ui = ExternalIdMixin.__dict__["_inject_external_ids_form_ui"]
    inject_external_ids_button = ExternalIdMixin.__dict__["_inject_external_ids_button"]
    inject_external_ids_page = ExternalIdMixin.__dict__["_inject_external_ids_page"]
    build_external_ids_page_arch = ExternalIdMixin.__dict__["_build_external_ids_page_arch"]
    inject_external_ids_form_ui = ExternalIdMixin.__dict__["_inject_external_ids_form_ui"]


@common.tagged(*common.UNIT_TAGS)
class TestViewsLoad(UnitTestCase):
    def test_inject_external_ids_button_and_page(self) -> None:
        view_definition = {
            "arch": """
                <form>
                    <sheet>
                        <div name="button_box"/>
                        <notebook>
                            <page string="Main" name="main"/>
                        </notebook>
                    </sheet>
                </form>
            """
        }

        injected = FakeExternalIdsUiModel.inject_external_ids_form_ui(view_definition, "form")
        architecture = injected["arch"]

        self.assertIn('button name="action_view_external_ids"', architecture)
        self.assertIn('field name="external_ids_count"', architecture)
        self.assertIn('page string="External IDs"', architecture)
        self.assertIn("default_res_model': 'external.id.fixture", architecture)

    def test_inject_external_ids_page_creates_notebook_when_missing(self) -> None:
        view_definition = {
            "arch": """
                <form>
                    <sheet>
                        <div name="button_box"/>
                        <group/>
                    </sheet>
                </form>
            """
        }

        injected = FakeExternalIdsUiModel.inject_external_ids_form_ui(view_definition, "form")

        self.assertIn("<notebook>", injected["arch"])
        self.assertIn('page string="External IDs"', injected["arch"])

    def test_inject_external_ids_ui_is_idempotent(self) -> None:
        view_definition = {
            "arch": """
                <form>
                    <sheet>
                        <div name="button_box">
                            <button name="action_view_external_ids" type="object"/>
                        </div>
                        <notebook>
                            <page string="External IDs" name="external_ids"/>
                        </notebook>
                    </sheet>
                </form>
            """
        }

        injected = FakeExternalIdsUiModel.inject_external_ids_form_ui(view_definition, "form")

        self.assertEqual(injected["arch"].count('button name="action_view_external_ids"'), 1)
        self.assertEqual(injected["arch"].count('name="external_ids"'), 1)
