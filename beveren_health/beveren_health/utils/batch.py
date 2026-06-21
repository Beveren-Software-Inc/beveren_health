# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.file_manager import save_file
import os
import re
import hashlib
from frappe.utils import getdate
import random

def sanitize_filename(filename):
    """
    Remove special characters and replace spaces with underscores.
    """
    filename = re.sub(r'[^\w\s.-]', '', str(filename))
    filename = filename.replace(" ", "_")
    return filename

def calculate_ean13_check_digit(number):
    """
    Calculate the check digit for EAN13 barcode.
    """
    total = 0
    for i, digit in enumerate(number):
        multiplier = 3 if i % 2 == 1 else 1
        total += int(digit) * multiplier
    
    check_digit = (10 - (total % 10)) % 10
    return check_digit

# def generate_barcode_number(item_code, batch_id, manufacturing_date, expiry_date):
#     """
#     Generate a unique EAN-13 barcode number based on item code, batch, 
#     manufacturing date, and expiry date
#     """
#     try:
#         # Get the component parts
#         item_code = item_code or ""
#         batch_id = batch_id or ""
#         mfg_date = getdate(manufacturing_date).strftime("%y%m%d") if manufacturing_date else ""
#         exp_date = getdate(expiry_date).strftime("%y%m%d") if expiry_date else ""
        
#         # Combine all parts to create a unique string
#         combined_string = f"{item_code}{batch_id}{mfg_date}{exp_date}"
        
#         # Generate a hash and take first 12 digits for EAN-13 base
#         hash_object = hashlib.sha256(combined_string.encode())
#         hash_hex = hash_object.hexdigest()
        
#         # Take first 12 digits from hash (ensure it's numeric)
#         base_number = ''.join(filter(str.isdigit, hash_hex))[:12]
        
#         # Ensure we have exactly 12 digits, pad if necessary
#         if len(base_number) < 12:
#             # Pad with zeros from hash if needed
#             additional_digits = ''.join(filter(str.isdigit, hash_hex[12:]))
#             base_number = base_number + additional_digits
#             base_number = base_number[:12].ljust(12, '0')
        
#         # Calculate check digit
#         check_digit = calculate_ean13_check_digit(base_number)
#         barcode = base_number + str(check_digit)
        
#         # Check if barcode already exists in Batch
#         if frappe.db.exists("Batch", {"custom_barcode": barcode}):
#             # If exists, try with a different approach
#             random_suffix = str(random.randint(10, 99))
#             base_number = base_number[:10] + random_suffix
#             check_digit = calculate_ean13_check_digit(base_number)
#             barcode = base_number + str(check_digit)
        
#         return barcode
        
#     except Exception as e:
#         frappe.log_error(
#             title="Barcode Generation Error",
#             message=f"Error generating barcode: {str(e)}"
#         )
#         frappe.throw(f"Could not generate barcode number: {str(e)}")

# @frappe.whitelist()
# def generate_barcode_image(barcode_value, doc_name, barcode_type="EAN13"):
#     """
#     Generate a barcode image for the given barcode value.
#     Returns the file URL for the saved image.
#     """
#     if not barcode_value:
#         return None
    
#     try:
#         # Import barcode library
#         try:
#             from barcode import EAN13, Code128, get_barcode_class
#             from barcode.writer import ImageWriter
#         except ImportError:
#             frappe.throw(
#                 "Please install barcode library: bench pip install python-barcode[images]"
#             )
        
#         # Get barcode class based on type
#         if barcode_type == "EAN13":
#             barcode_class = EAN13
#         elif barcode_type == "Code128":
#             barcode_class = Code128
#         else:
#             barcode_class = get_barcode_class(barcode_type)
#             if not barcode_class:
#                 frappe.throw(f"Unsupported barcode type: {barcode_type}")
        
#         # Sanitize filename
#         sanitized_filename = sanitize_filename(f"batch_{doc_name}_{barcode_value}")
        
#         # Get site path for temporary file storage
#         file_path = frappe.get_site_path(f"private/files/{sanitized_filename}.png")
        
#         # Ensure directory exists
#         dirname = os.path.dirname(file_path)
#         os.makedirs(dirname, exist_ok=True)
        
#         # Create barcode instance
#         barcode_instance = barcode_class(str(barcode_value), writer=ImageWriter())
        
#         # Save barcode image
#         try:
#             barcode_instance.save(file_path.replace(".png", ""), options={
#                 'format': 'PNG',
#                 'write_text': True,
#                 'quiet_zone': 2.0,
#                 'module_width': 0.3,
#                 'module_height': 15.0,
#                 'font_size': 10,
#                 'text_distance': 5,
#                 'dpi': 300
#             })
#         except Exception:
#             # Fallback to default save if options are not supported
#             barcode_instance.save(file_path.replace(".png", ""))
        
#         # Read the saved file
#         with open(file_path, "rb") as f:
#             file_content = f.read()
        
#         # Clean up temporary file
#         try:
#             os.remove(file_path)
#         except:
#             pass
        
#         # Save file using Frappe's file manager
#         file_doc = save_file(
#             f"{sanitized_filename}.png",
#             file_content,
#             "Batch",    # dt
#             doc_name,   # dn
#             is_private=0
#         )
        
#         return file_doc.file_url
        
#     except Exception as e:
#         frappe.log_error(
#             title="Barcode Image Generation Error",
#             message=f"Error generating barcode image: {str(e)}"
#         )
#         frappe.msgprint(f"Warning: Could not generate barcode image: {str(e)}")
#         return None


def validate_ean13_barcode(barcode):
    """
    Validate an EAN-13 barcode
    """
    if not barcode or len(barcode) != 13 or not barcode.isdigit():
        return False
    
    # Calculate check digit
    base = barcode[:-1]
    check_digit = int(barcode[-1])
    
    total = 0
    for i, digit in enumerate(base):
        multiplier = 3 if i % 2 == 1 else 1
        total += int(digit) * multiplier
    
    calculated_check = (10 - (total % 10)) % 10
    return calculated_check == check_digit

def batch_before_save(doc, method=None):
    """On Batch save: generate a new unique barcode for this batch and add it to Item's barcode table."""
    if not doc.item:
        return

    try:
        from beveren_health.beveren_health.utils.barcode import (
            DEFAULT_BARCODE_TYPE,
            generate_barcode_image,
            generate_ean13_barcode,
        )

        # Check if this batch already has a barcode row on the item
        existing = frappe.db.get_value(
            "Item Barcode",
            {"parent": doc.item, "custom_batch": doc.name},
            "name"
        )
        if existing:
            return  # Already linked, nothing to do

        # Generate a unique barcode value
        new_barcode = generate_ean13_barcode()
        if frappe.db.exists("Item Barcode", {"barcode": new_barcode}):
            new_barcode = generate_ean13_barcode()
            if frappe.db.exists("Item Barcode", {"barcode": new_barcode}):
                frappe.throw("Could not generate a unique barcode. Please try again.")

        image_path = generate_barcode_image(new_barcode, DEFAULT_BARCODE_TYPE)
        # Append a new dedicated row for this batch
        item = frappe.get_doc("Item", doc.item)
        item.append("barcodes", {
            "barcode": new_barcode,
            "barcode_type": DEFAULT_BARCODE_TYPE,
            "custom_image": image_path,
            "custom_batch": doc.name,   # link to this batch
        })
        item.flags.ignore_validate = True
        item.flags.ignore_mandatory = True
        item.save(ignore_permissions=True)

    except Exception:
        frappe.log_error(
            title="Batch → Item Barcode sync failed",
            message=frappe.get_traceback(),
        )

def batch_on_update(doc, method):
    """Handle updates if needed"""
    pass

def batch_on_change(doc, method):
    """Handle changes if needed"""
    pass

# Utility function for bulk operations

@frappe.whitelist()
def generate_barcode_for_existing_batches():
    """
    Generate barcodes for existing batches that don't have them
    """
    batches = frappe.get_all("Batch", 
        filters={
            "custom_barcode": ["is", "not set"],
            "docstatus": 0
        },
        pluck="name"
    )
    
    for batch_name in batches:
        try:
            batch = frappe.get_doc("Batch", batch_name)
            
            # Generate barcode number
            if not batch.custom_barcode:
                batch.custom_barcode = generate_barcode_number(
                    batch.item,
                    batch.batch_id,
                    batch.manufacturing_date,
                    batch.expiry_date
                )
            
            # Generate barcode image
            if batch.custom_barcode and not batch.custom_barcode_image:
                batch.custom_barcode_image = generate_barcode_image(
                    batch.custom_barcode,
                    batch.name
                )
            
            # Save changes
            batch.db_set({
                'custom_barcode': batch.custom_barcode,
                'custom_barcode_image': batch.custom_barcode_image
            })
            
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(
                title="Batch Barcode Generation Error",
                message=f"Error for batch {batch_name}: {str(e)}"
            )
    
    return f"Processed {len(batches)} batches"

def regenerate_barcode_image_for_batch(batch_name):
    """
    Regenerate barcode image for a specific batch
    """
    try:
        batch = frappe.get_doc("Batch", batch_name)
        
        if batch.custom_barcode:
            # Generate new image
            image_url = generate_barcode_image(
                batch.custom_barcode,
                batch.name
            )
            
            if image_url:
                batch.db_set('custom_barcode_image', image_url)
                return True, "Barcode image regenerated successfully"
            else:
                return False, "Failed to generate barcode image"
        else:
            return False, "Batch has no barcode number"
            
    except Exception as e:
        frappe.log_error(
            title="Batch Barcode Regeneration Error",
            message=f"Error for batch {batch_name}: {str(e)}"
        )
        return False, str(e)