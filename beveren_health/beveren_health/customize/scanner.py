import frappe
from frappe import _
import re
from datetime import datetime

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
    }
}
@frappe.whitelist()
def process_batch_scan(barcode_data, document_name, doctype, current_item_code=None, current_batch_no=None, warehouse=None):
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
            current_idx = get_current_row_index(doc, config, current_item_code, current_batch_no)
            
            # Check if the existing batch is on the current row
            if existing_row_info['index'] == current_idx:
                # Case 2: Same batch as current row → append serial only
                frappe.logger().info(f"Case 2: Same batch on current row - appending serial")
                return append_serial_to_row(doc, config, existing_row_info['row'], parsed, item)
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
                    "mfg_date": parsed.get('mfg_date')
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
        "batch_no": parsed['batch_no'],
        "serial_no": parsed.get('serial_no'),
        "expiry_date": parsed.get('expiry_date'),
        "mfg_date": parsed.get('mfg_date'),
        "qty": 1,
        "rate": frappe.db.get_value("Item Price", {"item_code": item.name, "buying": 1}, "price_list_rate") or 0,
        "warehouse": warehouse
    }

def append_serial_to_row(doc, config, row, parsed, item):
    """Case 2 – same batch scanned again: append serial, recalculate qty from serial count."""
    serial_no = row.serial_no or ''
    
    new_serial = parsed.get('serial_no')
    if new_serial and new_serial not in serial_no:
        serial_no = (serial_no + '\n' + new_serial).strip()
    
    # Qty = number of serials tracked (one unit per serial)
    serial_count = len([s for s in serial_no.split('\n') if s.strip()]) if serial_no else 1
    new_qty = serial_count if serial_no else (row.qty or 0) + 1
    new_amount = new_qty * (row.rate or 0)
    
    # Prepare update values
    update_values = {
        config['qty_field']: new_qty,
        config['amount_field']: new_amount,
        'serial_no': serial_no
    }
    
    # Add doctype-specific fields
    for field, source_field in config['additional_fields'].items():
        if source_field == 'qty':
            update_values[field] = new_qty
        elif source_field == 'amount':
            update_values[field] = new_amount
        elif source_field == 'rate':
            update_values[field] = row.rate
    
    frappe.db.set_value(config['child_doctype'], row.name, update_values)
    doc.reload()
    
    return {
        "success": True,
        "action": "append_serial",
        "row_name": row.name,
        "new_qty": new_qty,
        "new_amount": new_amount,
        "serial_no": parsed.get('serial_no'),
        "all_serials": serial_no,
        "item_name": item.item_name,
        "batch_no": parsed['batch_no']
    }

def create_new_row(config, item, parsed, warehouse=None):
    """Case 3 – different batch, current row already used: signal JS to add a new child row."""
    get_or_create_batch(item.name, parsed['batch_no'], parsed.get('expiry_date'))
    
    rate = frappe.db.get_value(
        "Item Price",
        {"item_code": item.name, "buying": 1},
        "price_list_rate"
    ) or 0
    
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
        "warehouse": warehouse
    }

# ─── Barcode parsing ──────────────────────────────────────────────────────────

def parse_barcode(barcode_data):
    """Parse GS1 barcode or return as batch number if not GS1 format."""
    if not barcode_data:
        return {'batch_no': None, 'serial_no': None, 'gtin': None,
                'expiry_date': None, 'mfg_date': None, 'raw': barcode_data}
    
    barcode_data = barcode_data.strip()
    
    if barcode_data.startswith('01'):
        return parse_gs1(barcode_data)
    else:
        return {'batch_no': barcode_data, 'serial_no': None, 'gtin': None,
                'expiry_date': None, 'mfg_date': None, 'raw': barcode_data}

def parse_gs1(raw_code):
    """Parse GS1 barcode by handling GS separators and fixed-length AIs properly."""
    result = {
        'batch_no': None, 'serial_no': None, 'gtin': None,
        'expiry_date': None, 'mfg_date': None, 'raw': raw_code
    }
    
    frappe.logger().info(f"Raw GS1 Code: {repr(raw_code)}")
    
    # Handle GS separator by splitting into logical segments
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
                for next_ai in ['01', '11', '17']:
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
    
    frappe.logger().info(f"Final parsed result: {result}")
    return result

def _parse_date(date_str):
    """Convert YYMMDD → YYYY-MM-DD."""
    try:
        yy = int(date_str[0:2])
        mm = date_str[2:4]
        dd = date_str[4:6]
        year = 2000 + yy if yy < 50 else 1900 + yy
        return f"{year}-{mm}-{dd}"
    except Exception:
        return None

# ─── Lookup helpers ───────────────────────────────────────────────────────────

def find_item_by_batch_or_serial(batch_no, serial_no=None):
    """Find item code from batch or serial number."""
    if batch_no:
        item = frappe.db.get_value("Batch", {"batch_id": batch_no}, "item")
        if item:
            return item
    if serial_no:
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

def get_current_row_index(doc, config, current_item_code, current_batch_no):
    """Get index of current row based on item code and batch number."""
    if not current_item_code:
        return -1
    
    items = doc.get(config['item_field'])
    for idx, row in enumerate(items):
        if row.item_code == current_item_code and row.batch_no == current_batch_no:
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