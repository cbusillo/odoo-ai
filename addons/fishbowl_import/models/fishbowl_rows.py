from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, TypeAdapter

FlagValue = bool | int | str | bytes | bytearray | memoryview | None


class FishbowlRow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, arbitrary_types_allowed=True)


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


class OrderRow(FishbowlRow):
    id: int
    num: str | None = None
    statusId: int | None = None
    customerId: int | None = None
    vendorId: int | None = None
    soId: int | None = None
    dateIssued: datetime | None = None
    dateCreated: datetime | None = None
    dateShipped: datetime | None = None
    customerPO: str | None = None
    note: str | None = None


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
    qtyShipped: float | None = None
    uomId: int | None = None


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


# noinspection DuplicatedCode
UNIT_ROWS_ADAPTER = TypeAdapter(list[UnitRow])
UNIT_CONVERSION_ROWS_ADAPTER = TypeAdapter(list[UnitConversionRow])
CUSTOMER_ROWS_ADAPTER = TypeAdapter(list[CustomerRow])
VENDOR_ROWS_ADAPTER = TypeAdapter(list[VendorRow])
ADDRESS_ROWS_ADAPTER = TypeAdapter(list[AddressRow])
ADDRESS_TYPE_ROWS_ADAPTER = TypeAdapter(list[AddressTypeRow])
COUNTRY_ROWS_ADAPTER = TypeAdapter(list[CountryRow])
STATE_ROWS_ADAPTER = TypeAdapter(list[StateRow])
PART_ROWS_ADAPTER = TypeAdapter(list[PartRow])
PRODUCT_ROWS_ADAPTER = TypeAdapter(list[ProductRow])
# noinspection DuplicatedCode
PART_TYPE_ROWS_ADAPTER = TypeAdapter(list[PartTypeRow])
PART_COST_ROWS_ADAPTER = TypeAdapter(list[PartCostRow])
PART_COST_HISTORY_ROWS_ADAPTER = TypeAdapter(list[PartCostHistoryRow])
SALES_PRICE_ROWS_ADAPTER = TypeAdapter(list[SalesPriceRow])
INVENTORY_ROWS_ADAPTER = TypeAdapter(list[InventoryRow])
STATUS_ROWS_ADAPTER = TypeAdapter(list[StatusRow])
ORDER_ROWS_ADAPTER = TypeAdapter(list[OrderRow])
SALES_ORDER_LINE_ROWS_ADAPTER = TypeAdapter(list[SalesOrderLineRow])
PURCHASE_ORDER_LINE_ROWS_ADAPTER = TypeAdapter(list[PurchaseOrderLineRow])
SHIPMENT_LINE_ROWS_ADAPTER = TypeAdapter(list[ShipmentLineRow])
RECEIPT_ITEM_ROWS_ADAPTER = TypeAdapter(list[ReceiptItemRow])
