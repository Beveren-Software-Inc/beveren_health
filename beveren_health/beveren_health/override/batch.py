

import frappe
from erpnext.stock.doctype.batch.batch import Batch



def before_save(self, method=None):
    # Runs when Batch is created/updated
    # Only run if batch is linked to a Purchase Receipt
    # validate_batch(self)
    if not self.reference_doctype or not self.reference_name:
        return

    if self.reference_doctype != "Purchase Receipt":
        return

    # Get Purchase Receipt
    pr = frappe.get_doc("Purchase Receipt", self.reference_name)

    # Find the item row that created this batch
    pr_item = None
    for item in pr.items:
        if item.batch_no == self.name or item.item_code == self.item:
            pr_item = item
            break

    if not pr_item:
        return

    # Custom fields from Purchase Receipt Item
    expiry_date = pr_item.custom_expiry_date
    manufacturing_date = pr_item.custom_manufacturing_date

    # Update Batch if needed
    changed = False

    if expiry_date and self.expiry_date != expiry_date:
        self.expiry_date = expiry_date
        changed = True

    if manufacturing_date and self.manufacturing_date != manufacturing_date:
        self.manufacturing_date = manufacturing_date
        changed = True

    if changed:
        frappe.msgprint("Batch dates updated from Purchase Receipt")
        
    # batch_before_save(self, method)
    

class CustomBatch(Batch):

    def validate(self):
        original_batch_id = self.batch_id
        existing_batch = frappe.db.get_value(
            "Batch",
            {"batch_id": self.batch_id},
            ["name", "item"],
            as_dict=True
        )
        if existing_batch and existing_batch.item != self.item:
            new_batch_id = f"{self.batch_id}_{self.item}"

            frappe.logger().info(
                f"Batch {self.batch_id} exists for {existing_batch.item}. "
                f"Changing to {new_batch_id}"
            )
      
            self.batch_id = new_batch_id
            self.name = new_batch_id
            self.custom_original_batch_id = original_batch_id
           
        super().validate()