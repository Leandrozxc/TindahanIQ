# TindahanIQ

Single-store retail business intelligence and AI advisory context for Filipino sari-sari stores and micro-retailers.

## Language

**Store**:
The single physical sari-sari retail shop whose catalog, inventory, and sales are analyzed in one TindahanIQ instance.
_Avoid_: Tindahan, shop, tenant, account

**Product**:
A distinct sellable good in the Store catalog with a unit cost, selling price, and tracked stock level.
_Avoid_: Item, good, merchandise

**SKU**:
The unique, uppercase product identifier string used to reference a Product across CSV imports, inventory, and sales.
_Avoid_: Product code, barcode, item ID

**Sales Transaction**:
A recorded customer purchase of one Product at a point in time, capturing quantity sold and historical unit price and unit cost snapshots.
_Avoid_: Purchase, order, sale record

**Stock Adjustment**:
An immutable, signed ledger entry recording any change to a Product's physical stock level.
_Avoid_: Inventory delta, stock change, audit log

**Restock**:
A positive Stock Adjustment that adds newly received supplier units to a Product's stock.
_Avoid_: Replenishment, purchase order, stock-in

**Spoilage**:
A negative Stock Adjustment that removes expired, damaged, or unsellable units from stock without generating revenue.
_Avoid_: Waste, shrinkage, write-off

