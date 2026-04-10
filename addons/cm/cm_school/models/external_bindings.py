from typing import Final

from odoo.addons.external_ids.models.external_reference import (
    ExternalIdBinding,
    ExternalResourceName,
    ExternalResourceReference,
    ExternalSystemCode,
    ExternalSystemReference,
    register_external_system_reference,
)


class CmDataSystemCode(ExternalSystemCode):
    CM_DATA = "cm_data"


class CmSchoolResourceName(ExternalResourceName):
    PRICING_CATALOG = "pricing_catalog"
    PRICING_LINE = "pricing_line"


class CmDataReference(ExternalSystemReference):
    @property
    def pricing_catalog(self) -> ExternalResourceReference:
        return self.resource(CmSchoolResourceName.PRICING_CATALOG)

    @property
    def pricing_line(self) -> ExternalResourceReference:
        return self.resource(CmSchoolResourceName.PRICING_LINE)


CM_DATA_PRICING_CATALOG_BINDING: Final[ExternalIdBinding] = ExternalIdBinding(
    system_code=CmDataSystemCode.CM_DATA,
    resource_name=CmSchoolResourceName.PRICING_CATALOG,
)

CM_DATA_PRICING_LINE_BINDING: Final[ExternalIdBinding] = ExternalIdBinding(
    system_code=CmDataSystemCode.CM_DATA,
    resource_name=CmSchoolResourceName.PRICING_LINE,
)


register_external_system_reference(CmDataSystemCode.CM_DATA, CmDataReference)
