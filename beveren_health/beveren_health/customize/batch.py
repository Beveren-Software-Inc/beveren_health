

import frappe 

def validate_batch(doc, method=None):
    existing_batch = frappe.db.get_value("Batch", {
        "batch_id": doc.batch_id
    }, ["name", "item"], as_dict=True)
    
    if existing_batch:
        # Batch exists for different item - create unique version
        unique_batch_id = f"{doc.batch_id}_{doc.item}"
        
        frappe.logger().info(f"Batch {doc.batch_id} already exists for item {existing_batch.item}. Creating {unique_batch_id} for {doc.item}")
        
        batch = frappe.get_doc({
            "doctype": "Batch",
            "batch_id": unique_batch_id,
            "custom_original_batch_id": doc.batch_id,  # Store original batch ID
            "item": doc.item,
            "expiry_date": doc.expiry_date
        })
        batch.insert(ignore_permissions=True)
        frappe.db.commit()
        return batch