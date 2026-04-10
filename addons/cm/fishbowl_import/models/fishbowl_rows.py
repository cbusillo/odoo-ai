from datetime import datetime
from typing import ClassVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, TypeAdapter

FlagValue = bool | int | str | bytes | bytearray | memoryview | None


class FishbowlRow(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", populate_by_name=True, arbitrary_types_allowed=True)


def build_rows_adapter(row_model: type[FishbowlRow]) -> TypeAdapter:
    return TypeAdapter(list[row_model])


def build_rows_adapters(*row_models: type[FishbowlRow]) -> tuple[TypeAdapter, ...]:
    return tuple(build_rows_adapter(row_model) for row_model in row_models)


class UnitRow(FishbowlRow):
    id: int
    name: str | None = None
    code: str | None = None
    uomType: int | None = None
    defaultRecord: FlagValue = None
    integral: FlagValue = None
    activeFlag: FlagValue = None


class UnitConversionRow(FishbowlRow):
    fromUomId: int
    toUomId: int
    factor: float | None = None
    multiply: float | None = None


class CustomerRow(FishbowlRow):
    id: int
    accountId: int | None = None
    number: str | None = None
    name: str | None = None
    note: str | None = None
    activeFlag: FlagValue = None


class VendorRow(FishbowlRow):
    id: int
    accountId: int | None = None
    name: str | None = None
    accountNum: str | None = None
    note: str | None = None
    activeFlag: FlagValue = None


class AddressRow(FishbowlRow):
    id: int
    accountId: int | None = None
    name: str | None = None
    addressName: str | None = None
    address: str | None = None
    city: str | None = None
    stateId: int | None = None
    countryId: int | None = None
    zip: str | None = None
    typeId: int | None = None


class AddressTypeRow(FishbowlRow):
    id: int
    name: str | None = None


class CountryRow(FishbowlRow):
    id: int
    name: str | None = None
    abbreviation: str | None = None


class StateRow(FishbowlRow):
    id: int
    countryConstID: int | None = None
    name: str | None = None
    code: str | None = None


class PartRow(FishbowlRow):
    id: int
    num: str | None = None
    description: str | None = None
    details: str | None = None
    uomId: int | None = None
    typeId: int | None = None
    trackingFlag: FlagValue = None
    serializedFlag: FlagValue = None
    stdCost: float | None = None
    activeFlag: FlagValue = None


class ProductRow(FishbowlRow):
    id: int
    partId: int | None = None
    num: str | None = None
    description: str | None = None
    price: float | None = None
    uomId: int | None = None
    activeFlag: FlagValue = None


class PartTypeRow(FishbowlRow):
    id: int
    name: str | None = None


class PartCostRow(FishbowlRow):
    partId: int | None = Field(default=None, validation_alias=AliasChoices("partId", "PARTID"))
    avgCost: float | None = Field(default=None, validation_alias=AliasChoices("avgCost", "AVGCOST"))


class PartCostHistoryRow(FishbowlRow):
    partId: int | None = None
    avgCost: float | None = None
    dateCaptured: datetime | None = None


class SalesPriceRow(FishbowlRow):
    id: int
    productId: int | None = None
    unitPrice: float | None = None
    dateIssued: datetime | None = None
    dateCreated: datetime | None = None


class InventoryRow(FishbowlRow):
    partId: int | None = Field(default=None, validation_alias=AliasChoices("partId", "PARTID"))
    qtyOnHand: float | None = Field(default=None, validation_alias=AliasChoices("qtyOnHand", "QTYONHAND"))


class StatusRow(FishbowlRow):
    id: int
    name: str | None = None


class OrderRowBase(FishbowlRow):
    id: int
    num: str | None = None
    statusId: int | None = None
    dateIssued: datetime | None = None
    dateCreated: datetime | None = None
    note: str | None = None


class OrderRow(OrderRowBase):
    customerId: int | None = None
    vendorId: int | None = None
    soId: int | None = None
    dateShipped: datetime | None = None
    customerPO: str | None = None


# noinspection DuplicatedCode
class SalesOrderLineRow(FishbowlRow):
    id: int
    soId: int | None = None
    productId: int | None = None
    productNum: str | None = None
    description: str | None = None
    qtyOrdered: float | None = None
    unitPrice: float | None = None
    uomId: int | None = None


# noinspection DuplicatedCode
class PurchaseOrderLineRow(FishbowlRow):
    id: int
    poId: int | None = None
    partId: int | None = None
    partNum: str | None = None
    description: str | None = None
    qtyToFulfill: float | None = None
    unitCost: float | None = None
    uomId: int | None = None


class ShipmentLineRow(FishbowlRow):
    id: int
    shipId: int | None = None
    soItemId: int | None = None
    xoItemId: int | None = None
    itemId: int | None = None
    qtyShipped: float | None = None
    uomId: int | None = None


# noinspection DuplicatedCode
# Fishbowl row models intentionally mirror upstream schemas for traceability.
class TransferOrderLineRow(FishbowlRow):
    id: int
    partId: int | None = None
    partNum: str | None = None


# noinspection DuplicatedCode
class ReceiptItemRow(FishbowlRow):
    id: int
    receiptId: int | None = None
    poItemId: int | None = None
    qty: float | None = None
    uomId: int | None = None
    dateReceived: datetime | None = None
    partId: int | None = None
    poId: int | None = None


(
    UNIT_ROWS_ADAPTER,
    UNIT_CONVERSION_ROWS_ADAPTER,
    CUSTOMER_ROWS_ADAPTER,
    VENDOR_ROWS_ADAPTER,
    ADDRESS_ROWS_ADAPTER,
    ADDRESS_TYPE_ROWS_ADAPTER,
    COUNTRY_ROWS_ADAPTER,
    STATE_ROWS_ADAPTER,
    PART_ROWS_ADAPTER,
    PRODUCT_ROWS_ADAPTER,
    PART_TYPE_ROWS_ADAPTER,
    PART_COST_ROWS_ADAPTER,
    PART_COST_HISTORY_ROWS_ADAPTER,
    SALES_PRICE_ROWS_ADAPTER,
    INVENTORY_ROWS_ADAPTER,
    STATUS_ROWS_ADAPTER,
    ORDER_ROWS_ADAPTER,
    SALES_ORDER_LINE_ROWS_ADAPTER,
    PURCHASE_ORDER_LINE_ROWS_ADAPTER,
    SHIPMENT_LINE_ROWS_ADAPTER,
    TRANSFER_ORDER_LINE_ROWS_ADAPTER,
    RECEIPT_ITEM_ROWS_ADAPTER,
) = build_rows_adapters(
    UnitRow,
    UnitConversionRow,
    CustomerRow,
    VendorRow,
    AddressRow,
    AddressTypeRow,
    CountryRow,
    StateRow,
    PartRow,
    ProductRow,
    PartTypeRow,
    PartCostRow,
    PartCostHistoryRow,
    SalesPriceRow,
    InventoryRow,
    StatusRow,
    OrderRow,
    SalesOrderLineRow,
    PurchaseOrderLineRow,
    ShipmentLineRow,
    TransferOrderLineRow,
    ReceiptItemRow,
)
