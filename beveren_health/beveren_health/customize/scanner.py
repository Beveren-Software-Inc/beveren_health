import frappe
from frappe import _
import re
from datetime import datetime

from beveren_health.beveren_health.customize.dispensing_lot import (
	DISPENSING_LOT_FIELD,
	split_dispensing_lots,
)

# Document type configurations
DOCTYPE_CONFIG = {
    "Purchase Receipt": {
        "child_doctype": "Purchase Receipt Item",
        "item_field": "items",
        "qty_field": "qty",
        "amount_field": "amount",
        "rate_field": "rate",
        "additional_fields": {}
    },
    "Stock Reconciliation": {
        "child_doctype": "Stock Reconciliation Item",
        "item_field": "items",
        "qty_field": "qty",
        "amount_field": "amount",
        "rate_field": "rate",
        "gtin_field": "custom_gstin",
        "expiry_field": "expiry_date",
        "expiry_field_extra": "custom_expiry_date",
        "mfg_field": "custom_manufacturing_date",
        "additional_fields": {
            "current_qty": "qty",
            "current_amount": "amount"
        }
    },
    "Stock Entry": {
        "child_doctype": "Stock Entry Detail",
        "item_field": "items",
        "qty_field": "qty",
        "amount_field": "amount",
        "rate_field": "rate",
        "additional_fields": {
            "transfer_qty": "qty",
            "basic_rate": "rate",
            "basic_amount": "amount"
        }
    },
    "Stock Scanner": {
        "child_doctype": "Stock Scanner Item",
        "item_field": "items",
        "qty_field": "qty",
        "amount_field": "amount",
        "rate_field": "valuation_rate",
        "lot_field": "serial_no",
        "gtin_field": "gtin",
        "expiry_field": "expiry_date",
        "mfg_field": "manufacturing_date",
        "additional_fields": {
            "current_qty": "qty",
            "current_amount": "amount"
        }
    },
}


def _lot_field(config):
    return config.get("lot_field") or DISPENSING_LOT_FIELD


def _apply_parsed_metadata(update_values, row, parsed, config, only_if_empty=False):
    """Map barcode GTIN / expiry / mfg onto the child row fields for this doctype."""
    gtin_field = config.get("gtin_field") or "custom_gstin"
    expiry_field = config.get("expiry_field") or "expiry_date"
    expiry_extra = config.get("expiry_field_extra")
    mfg_field = config.get("mfg_field") or "custom_manufacturing_date"

    gtin_val = parsed.get("gtin")
    if gtin_val and (not only_if_empty or not row.get(gtin_field)):
        update_values[gtin_field] = gtin_val

    expiry_val = parsed.get("expiry_date")
    if expiry_val and (not only_if_empty or not row.get(expiry_field)):
        update_values[expiry_field] = expiry_val
        if expiry_extra:
            update_values[expiry_extra] = expiry_val

    mfg_val = parsed.get("mfg_date")
    if mfg_val and (not only_if_empty or not row.get(mfg_field)):
        update_values[mfg_field] = mfg_val
@frappe.whitelist()
def process_batch_scan(
	barcode_data,
	document_name,
	doctype,
	current_item_code=None,
	current_batch_no=None,
	warehouse=None,
	current_row_name=None,
):
    """
    Unified barcode scanner handler for Purchase Receipt, Stock Reconciliation, and Stock Entry.
    
    Cases:
    1. Current row has no batch yet → assign batch + serial to current row
    2. Scanned batch == current row batch → just append serial (same batch)
    3. Scanned batch not in document, but current row already has a batch → create new row
    4. Scanned batch exists on a DIFFERENT row → move cursor there, append serial
    """
    try:
        # Validate doctype
        if doctype not in DOCTYPE_CONFIG:
            return {
                "success": False,
                "message": f"Unsupported document type: {doctype}"
            }
        
        config = DOCTYPE_CONFIG[doctype]
        
        # Parse barcode
        parsed = parse_barcode(barcode_data)
        frappe.logger().info(f"GS1 Parser Result for {doctype}: {parsed}")
        
        if not parsed.get('batch_no'):
            return {
                "success": False,
                "message": f"Batch number not found in barcode. Parsed: {parsed}. Raw: {barcode_data}"
            }
        
        # Get the document
        doc = frappe.get_doc(doctype, document_name)
        
        # Find item by batch/serial lookup
        item_code = find_item_by_batch_or_serial(parsed['batch_no'], parsed.get('serial_no'))
        if not item_code and current_item_code:
            item_code = current_item_code
        if not item_code:
            return {"success": False, "message": "Cannot determine item for this barcode"}
        
        item = frappe.get_cached_doc("Item", item_code)
        
        # Find if this batch already exists anywhere in the document
        existing_row_info = find_existing_batch_row(doc, config, item_code, parsed['batch_no'])
        
        if existing_row_info:
            current_idx = get_current_row_index(
				doc, config, current_item_code, current_batch_no, current_row_name
			)
            
            # Check if the existing batch is on the current row
            if existing_row_info['index'] == current_idx:
                # Case 2: Same batch as current row → append serial only
                frappe.logger().info(f"Case 2: Same batch on current row - appending serial")
                return append_dispensing_lot_to_row(doc, config, existing_row_info['row'], parsed, item)
            else:
                # Case 4: Batch lives on a different row → move focus there
                frappe.logger().info(f"Case 4: Batch exists on different row (index {existing_row_info['index']}) - moving focus")
                return {
                    "success": True,
                    "action": "move_to_existing",
                    "existing_row_index": existing_row_info['index'],
                    "row_name": existing_row_info['row'].name,
                    "batch_no": parsed['batch_no'],
                    "serial_no": parsed.get('serial_no'),
                    "item_code": item_code,
                    "item_name": item.item_name,
                    "expiry_date": parsed.get('expiry_date'),
                    "mfg_date": parsed.get('mfg_date'),
                    "gtin": parsed.get('gtin')
                }
        else:
            # Batch doesn't exist anywhere in document
            # Check if current row already has a batch (any batch)
            if current_batch_no and current_batch_no.strip():
                # Current row has a batch, and it's different from scanned batch
                # Case 3: Different batch → create new row
                frappe.logger().info(f"Case 3: Current row has batch '{current_batch_no}', scanned batch '{parsed['batch_no']}' is different - creating new row")
                return create_new_row(config, item, parsed, warehouse)
            else:
                # Case 1: Current row has no batch yet → assign to current row
                frappe.logger().info(f"Case 1: Current row has no batch - assigning to current row")
                return assign_to_current_row(config, item, parsed, warehouse)
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"{doctype} Scanner Error")
        return {"success": False, "message": str(e)}

# ─── Action helpers ───────────────────────────────────────────────────────────

def assign_to_current_row(config, item, parsed, warehouse=None):
    """Case 1 – first scan on an empty row: assign batch + serial."""
    get_or_create_batch(item.name, parsed['batch_no'], parsed.get('expiry_date'))
    
    return {
        "success": True,
        "action": "assign_to_current",
        "item_code": item.name,
        "item_name": item.item_name,
        "uom": item.stock_uom,
        "batch_no": parsed['batch_no'],
        "serial_no": parsed.get('serial_no'),
        "expiry_date": parsed.get('expiry_date'),
        "mfg_date": parsed.get('mfg_date'),
        "qty": 1,
        "rate": frappe.db.get_value("Item Price", {"item_code": item.name, "buying": 1}, "price_list_rate") or 0,
        "warehouse": warehouse,
        "gtin": parsed.get('gtin'),
    }


def append_dispensing_lot_to_row(doc, config, row, parsed, item):
    """Case 2 – same batch scanned again: append dispensing lot, recalculate qty."""
    lot_field = _lot_field(config)
    dispensing_lots = row.get(lot_field) or ""

    new_serial = parsed.get("serial_no")
    existing = split_dispensing_lots(dispensing_lots)
    if new_serial and new_serial not in existing:
        existing.append(new_serial)
        dispensing_lots = "\n".join(existing)

    lot_count = len(split_dispensing_lots(dispensing_lots)) if dispensing_lots else 1
    new_qty = lot_count if dispensing_lots else (row.qty or 0) + 1

    rate = 0
    if hasattr(row, "rate"):
        rate = row.rate or 0
    elif hasattr(row, "basic_rate"):
        rate = row.basic_rate or 0
    elif config.get("rate_field"):
        rate = getattr(row, config["rate_field"], 0) or 0

    new_amount = new_qty * rate

    update_values = {
        config["qty_field"]: new_qty,
        config["amount_field"]: new_amount,
        lot_field: dispensing_lots,
    }

    _apply_parsed_metadata(update_values, row, parsed, config, only_if_empty=True)

    if hasattr(row, "rate"):
        update_values["rate"] = rate
    elif hasattr(row, "basic_rate"):
        update_values["basic_rate"] = rate

    for field, source_field in config["additional_fields"].items():
        if source_field == "qty":
            update_values[field] = new_qty
        elif source_field == "amount":
            update_values[field] = new_amount
        elif source_field == "rate":
            update_values[field] = rate

    frappe.db.set_value(config["child_doctype"], row.name, update_values)
    doc.reload()

    return {
        "success": True,
        "action": "append_serial",
        "row_name": row.name,
        "new_qty": new_qty,
        "new_amount": new_amount,
        "serial_no": parsed.get("serial_no"),
        "dispensing_lot": parsed.get("serial_no"),
        "all_dispensing_lots": dispensing_lots,
        "all_serials": dispensing_lots,
        "item_name": item.item_name,
        "batch_no": parsed["batch_no"],
        "gtin": parsed.get("gtin"),
        "expiry_date": parsed.get("expiry_date"),
        "mfg_date": parsed.get("mfg_date"),
    }
    
# def append_serial_to_row(doc, config, row, parsed, item):
#     """Case 2 – same batch scanned again: append serial, recalculate qty from serial count."""
#     serial_no = row.serial_no or ''
    
#     new_serial = parsed.get('serial_no')
#     if new_serial and new_serial not in serial_no:
#         serial_no = (serial_no + '\n' + new_serial).strip()
    
#     # Qty = number of serials tracked (one unit per serial)
#     serial_count = len([s for s in serial_no.split('\n') if s.strip()]) if serial_no else 1
#     new_qty = serial_count if serial_no else (row.qty or 0) + 1
#     new_amount = new_qty * (row.rate or 0)
    
#     # Prepare update values
#     update_values = {
#         config['qty_field']: new_qty,
#         config['amount_field']: new_amount,
#         'serial_no': serial_no
#     }
    
#     # Also update custom_gstin if present in parsed and not already set on row
#     if parsed.get('gtin') and not row.get('custom_gstin'):
#         update_values['custom_gstin'] = parsed.get('gtin')
    
#     # Add doctype-specific fields
#     for field, source_field in config['additional_fields'].items():
#         if source_field == 'qty':
#             update_values[field] = new_qty
#         elif source_field == 'amount':
#             update_values[field] = new_amount
#         elif source_field == 'rate':
#             update_values[field] = row.rate
    
#     frappe.db.set_value(config['child_doctype'], row.name, update_values)
#     doc.reload()
    
#     return {
#         "success": True,
#         "action": "append_serial",
#         "row_name": row.name,
#         "new_qty": new_qty,
#         "new_amount": new_amount,
#         "serial_no": parsed.get('serial_no'),
#         "all_serials": serial_no,
#         "item_name": item.item_name,
#         "batch_no": parsed['batch_no'],
#         "gtin": parsed.get('gtin')  # ADD THIS LINE
#     }
# def append_serial_to_row(doc, config, row, parsed, item):
#     """Case 2 – same batch scanned again: append serial, recalculate qty from serial count."""
#     serial_no = row.serial_no or ''
    
#     new_serial = parsed.get('serial_no')
#     if new_serial and new_serial not in serial_no:
#         serial_no = (serial_no + '\n' + new_serial).strip()
    
#     # Qty = number of serials tracked (one unit per serial)
#     serial_count = len([s for s in serial_no.split('\n') if s.strip()]) if serial_no else 1
#     new_qty = serial_count if serial_no else (row.qty or 0) + 1
#     new_amount = new_qty * (row.rate or 0)
    
#     # Prepare update values
#     update_values = {
#         config['qty_field']: new_qty,
#         config['amount_field']: new_amount,
#         'serial_no': serial_no
#     }
    
#     # Add doctype-specific fields
#     for field, source_field in config['additional_fields'].items():
#         if source_field == 'qty':
#             update_values[field] = new_qty
#         elif source_field == 'amount':
#             update_values[field] = new_amount
#         elif source_field == 'rate':
#             update_values[field] = row.rate
    
#     frappe.db.set_value(config['child_doctype'], row.name, update_values)
#     doc.reload()
    
#     return {
#         "success": True,
#         "action": "append_serial",
#         "row_name": row.name,
#         "new_qty": new_qty,
#         "new_amount": new_amount,
#         "serial_no": parsed.get('serial_no'),
#         "all_serials": serial_no,
#         "item_name": item.item_name,
#         "batch_no": parsed['batch_no']
#     }

def create_new_row(config, item, parsed, warehouse=None):
    """Case 3 – different batch, current row already used: signal JS to add a new child row."""
    get_or_create_batch(item.name, parsed['batch_no'], parsed.get('expiry_date'))
    
    rate = frappe.db.get_value(
        "Item Price",
        {"item_code": item.name, "buying": 1},
        "price_list_rate"
    ) or 0
    # DEBUG
    return {
        "success": True,
        "action": "create_new_row",
        "item_code": item.name,
        "item_name": item.item_name,
        "uom": item.stock_uom,
        "rate": rate,
        "amount": rate,
        "qty": 1,
        "batch_no": parsed['batch_no'],
        "serial_no": parsed.get('serial_no'),
        "expiry_date": parsed.get('expiry_date'),
        "mfg_date": parsed.get('mfg_date'),
        "warehouse": warehouse,
        "gtin": parsed.get('gtin')
    }

# ─── Barcode parsing ──────────────────────────────────────────────────────────

# def parse_barcode(barcode_data):
#     """Parse GS1 barcode or return as batch number if not GS1 format."""
#     if not barcode_data:
#         return {'batch_no': None, 'serial_no': None, 'gtin': None,
#                 'expiry_date': None, 'mfg_date': None, 'raw': barcode_data}
    
#     barcode_data = barcode_data.strip()
    
#     if barcode_data.startswith('01'):
#         return parse_gs1(barcode_data)
#     else:
#         return {'batch_no': barcode_data, 'serial_no': None, 'gtin': None,
#                 'expiry_date': None, 'mfg_date': None, 'raw': barcode_data}

def parse_barcode(barcode_data):
    """Parse GS1 barcode supporting multiple formats:
    1. Parentheses format: (01)GTIN(21)Serial(17)EXP(10)Batch
    2. Raw GS1 with/without separators
    3. Simple batch number
    """
    if not barcode_data:
        return {'batch_no': None, 'serial_no': None, 'gtin': None,
                'expiry_date': None, 'mfg_date': None, 'raw': barcode_data}
    
    barcode_data = barcode_data.strip()
    
    # Check if it's the parentheses format (contains ')' and '(' pattern)
    if ')' in barcode_data and '(' in barcode_data:
        return parse_parentheses_gs1(barcode_data)
    # Check if it starts with '01' (raw GS1 format)
    elif barcode_data.startswith('01'):
        return parse_gs1(barcode_data)
    else:
        # Simple batch number only
        return {'batch_no': barcode_data, 'serial_no': None, 'gtin': None,
                'expiry_date': None, 'mfg_date': None, 'raw': barcode_data}

def parse_parentheses_gs1(raw_code):
    """
    Parse GS1 barcode in parentheses format:
    (01)GTIN(21)Serial(17)EXP(10)Batch
    
    Example: (01)08002660032249(21)100285731569(17)270731(10)729323
    """
    result = {
        'batch_no': None, 
        'serial_no': None, 
        'gtin': None,
        'expiry_date': None, 
        'mfg_date': None, 
        'raw': raw_code
    }
    
    frappe.logger().info(f"Parsing parentheses GS1: {raw_code}")
    
    # Find all patterns like (XX)value
    # Using regex to find all occurrences of (digits) followed by content until next ( or end
    pattern = r'\((\d{2})\)([^\(]*)'
    matches = re.findall(pattern, raw_code)
    
    for ai, value in matches:
        value = value.strip()
        
        if ai == '01':
            result['gtin'] = value
            frappe.logger().info(f"Found GTIN: {value}")
        
        elif ai == '10':
            result['batch_no'] = value
            frappe.logger().info(f"Found Batch: {value}")
        
        elif ai == '11':
            result['mfg_date'] = _parse_date(value)
            frappe.logger().info(f"Found MFG Date: {value} -> {result['mfg_date']}")
        
        elif ai == '17':
            result['expiry_date'] = _parse_date(value)
            frappe.logger().info(f"Found EXP Date: {value} -> {result['expiry_date']}")
        
        elif ai == '21':
            result['serial_no'] = value
            frappe.logger().info(f"Found Serial: {value}")
        
        else:
            frappe.logger().warning(f"Unknown AI in parentheses format: {ai} = {value}")
    
    # Also check for custom_gstin if present (some formats might use different AI)
    # For now, we don't have a specific AI for GSTIN, but if needed:
    # Look for AI '30' or '241' or other common GSTIN identifiers
    gstin_pattern = r'\(30\)([^\(]*)'  # Example: AI 30 sometimes used for GSTIN
    gstin_match = re.search(gstin_pattern, raw_code)
    if gstin_match:
        result['gtin'] = gstin_match.group(1).strip()
    
    frappe.logger().info(f"Parentheses parse result: {result}")
    return result

# def parse_gs1(raw_code):
#     """Parse GS1 barcode by handling GS separators and fixed-length AIs properly."""
#     result = {
#         'batch_no': None, 'serial_no': None, 'gtin': None,
#         'expiry_date': None, 'mfg_date': None, 'raw': raw_code
#     }
    
#     frappe.logger().info(f"Raw GS1 Code: {repr(raw_code)}")
    
#     # Handle GS separator by splitting into logical segments
#     segments = []
#     if '\x1d' in raw_code:
#         segments = raw_code.split('\x1d')
#     else:
#         segments = [raw_code]
    
#     for segment in segments:
#         if not segment:
#             continue
        
#         pos = 0
#         seg_len = len(segment)
        
#         while pos < seg_len:
#             if pos + 2 > seg_len:
#                 break
            
#             ai = segment[pos:pos+2]
            
#             if ai == '01' and pos + 2 + 14 <= seg_len:
#                 result['gtin'] = segment[pos+2:pos+2+14]
#                 pos += 2 + 14
            
#             elif ai == '11' and pos + 2 + 6 <= seg_len:
#                 result['mfg_date'] = _parse_date(segment[pos+2:pos+2+6])
#                 pos += 2 + 6
            
#             elif ai == '17' and pos + 2 + 6 <= seg_len:
#                 result['expiry_date'] = _parse_date(segment[pos+2:pos+2+6])
#                 pos += 2 + 6
            
#             elif ai == '10':
#                 # Batch - variable length
#                 remaining = segment[pos+2:]
#                 next_ai_pos = len(remaining)
#                 for next_ai in ['01', '11', '17']:
#                     found = remaining.find(next_ai)
#                     if found != -1 and found < next_ai_pos:
#                         next_ai_pos = found
#                 result['batch_no'] = remaining[:next_ai_pos]
#                 pos = seg_len
            
#             elif ai == '21':
#                 # Serial - variable length, usually last field
#                 result['serial_no'] = segment[pos+2:]
#                 pos = seg_len
            
#             else:
#                 # Unknown AI, skip ahead by 1
#                 pos += 1
    
#     frappe.logger().info(f"Final parsed result: {result}")
#     return result

def parse_gs1(raw_code):
    """
    Parse raw GS1 barcode (without parentheses) by handling GS separators and fixed-length AIs.
    """
    result = {
        'batch_no': None, 
        'serial_no': None, 
        'gtin': None,
        'expiry_date': None, 
        'mfg_date': None, 
        'raw': raw_code
    }
    
    frappe.logger().info(f"Raw GS1 Code: {repr(raw_code)}")
    
    # First, try to see if it has the GS separator
    segments = []
    if '\x1d' in raw_code:
        segments = raw_code.split('\x1d')
    else:
        segments = [raw_code]
    
    for segment in segments:
        if not segment:
            continue
        
        pos = 0
        seg_len = len(segment)
        
        while pos < seg_len:
            if pos + 2 > seg_len:
                break
            
            ai = segment[pos:pos+2]
            
            if ai == '01' and pos + 2 + 14 <= seg_len:
                result['gtin'] = segment[pos+2:pos+2+14]
                pos += 2 + 14
            
            elif ai == '11' and pos + 2 + 6 <= seg_len:
                result['mfg_date'] = _parse_date(segment[pos+2:pos+2+6])
                pos += 2 + 6
            
            elif ai == '17' and pos + 2 + 6 <= seg_len:
                result['expiry_date'] = _parse_date(segment[pos+2:pos+2+6])
                pos += 2 + 6
            
            elif ai == '10':
                # Batch - variable length
                remaining = segment[pos+2:]
                next_ai_pos = len(remaining)
                for next_ai in ['01', '11', '17', '21']:
                    found = remaining.find(next_ai)
                    if found != -1 and found < next_ai_pos:
                        next_ai_pos = found
                result['batch_no'] = remaining[:next_ai_pos]
                pos = seg_len
            
            elif ai == '21':
                # Serial - variable length, usually last field
                result['serial_no'] = segment[pos+2:]
                pos = seg_len
            
            else:
                # Unknown AI, skip ahead by 1
                pos += 1
    
    frappe.logger().info(f"Raw GS1 parse result: {result}")
    return result


def _parse_date(date_str):
    """Convert YYMMDD → YYYY-MM-DD."""
    try:
        # Handle both 6-digit (YYMMDD) and 4-digit (YYMM) formats
        if len(date_str) == 6:
            yy = int(date_str[0:2])
            mm = date_str[2:4]
            dd = date_str[4:6]
            year = 2000 + yy if yy < 50 else 1900 + yy
            return f"{year}-{mm}-{dd}"
        elif len(date_str) == 4:
            # Handle YYMM format (first day of month)
            yy = int(date_str[0:2])
            mm = date_str[2:4]
            year = 2000 + yy if yy < 50 else 1900 + yy
            return f"{year}-{mm}-01"
        else:
            return None
    except Exception as e:
        frappe.logger().warning(f"Date parse error for '{date_str}': {e}")
        return None

# ─── Lookup helpers ───────────────────────────────────────────────────────────

def find_item_by_batch_or_serial(batch_no, serial_no=None):
    """Find item code from batch or serial number."""
    if batch_no:
        item = frappe.db.get_value("Batch", {"batch_id": batch_no}, "item")
        if item:
            return item
    if serial_no:
        item = frappe.db.get_value("Dispensing Lot", {"serial_no": serial_no}, "item")
        if item:
            return item
        item = frappe.db.get_value("Serial No", {"serial_no": serial_no}, "item_code")
        if item:
            return item
    return None

def find_existing_batch_row(doc, config, item_code, batch_no):
    """Find if batch already exists in document items."""
    frappe.logger().info(f"Looking for batch '{batch_no}' with item '{item_code}' in {doc.doctype} items")
    items = doc.get(config['item_field'])
    
    for idx, row in enumerate(items):
        frappe.logger().info(f"Row {idx}: item_code={row.item_code}, batch_no={row.batch_no}")
        if row.item_code == item_code and row.batch_no == batch_no:
            frappe.logger().info(f"Found matching row at index {idx}")
            return {'index': idx, 'row': row}
    
    frappe.logger().info("No matching row found")
    return None

def get_current_row_index(doc, config, current_item_code, current_batch_no, current_row_name=None):
    """Get index of the row being scanned (prefer row name, then item+batch)."""
    items = doc.get(config["item_field"]) or []

    if current_row_name:
        for idx, row in enumerate(items):
            if row.name == current_row_name:
                return idx

    if not current_item_code and not current_batch_no:
        return -1

    for idx, row in enumerate(items):
        row_batch = row.batch_no or ""
        if row.item_code == current_item_code and row_batch == (current_batch_no or ""):
            return idx

    return -1

def get_or_create_batch(item_code, batch_no, expiry_date=None):
    """Create or get batch with duplicate handling for same batch across different items."""
    if not batch_no:
        return None
    
    # Step 1: Try to find existing batch for this exact item by batch_id
    batch_name = frappe.db.get_value("Batch", {
        "batch_id": batch_no, 
        "item": item_code
    }, "name")
    
    if batch_name:
        return frappe.get_cached_doc("Batch", batch_name)
    
    # Step 2: Try to find by original_batch_id for this item
    batch_name = frappe.db.get_value("Batch", {
        "custom_original_batch_id": batch_no, 
        "item": item_code
    }, "name")
    
    if batch_name:
        frappe.logger().info(f"Found batch {batch_name} by original_batch_id {batch_no} for item {item_code}")
        return frappe.get_cached_doc("Batch", batch_name)
    
    # Step 3: Check if this batch exists for a DIFFERENT item
    existing_batch = frappe.db.get_value("Batch", {
        "batch_id": batch_no
    }, ["name", "item"], as_dict=True)
    
    if existing_batch:
        # Batch exists for different item - create unique version
        unique_batch_id = f"{batch_no}_{item_code}"
        
        frappe.logger().info(f"Batch {batch_no} already exists for item {existing_batch.item}. Creating {unique_batch_id} for {item_code}")
        
        batch = frappe.get_doc({
            "doctype": "Batch",
            "batch_id": unique_batch_id,
            "custom_original_batch_id": batch_no,
            "item": item_code,
            "expiry_date": expiry_date
        })
        batch.insert(ignore_permissions=True)
        frappe.db.commit()
        return batch
    
    # Step 4: No conflict - create batch normally
    frappe.logger().info(f"Creating new batch {batch_no} for item {item_code}")
    
    batch = frappe.get_doc({
        "doctype": "Batch",
        "batch_id": batch_no,
        "custom_original_batch_id": batch_no,
        "item": item_code,
        "expiry_date": expiry_date
    })
    batch.insert(ignore_permissions=True)
    frappe.db.commit()
    return batch
