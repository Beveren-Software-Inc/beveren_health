# Copyright (c) 2026, Beveren Software and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TrainingNeedAssessment(Document):
    def validate(self):
        for row in self.assessments:
            if row.not_applicable:
                row.ratings = 0
        applicable_rows = [row for row in self.assessments if not row.not_applicable]
        self.total_rating = sum(row.ratings * 5 or 0 for row in applicable_rows if row.ratings)
        self.total__achieved = (self.total_rating / (len(applicable_rows) * 5)) * 100 or 0

@frappe.whitelist()
def get_instructions():
    doc = frappe.get_single("TNA Rating Instruction")
    return [doc.instructions, doc.text1]