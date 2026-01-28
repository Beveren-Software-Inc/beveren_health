// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

frappe.ui.form.on("Purchase Receipt Item", {
	custom_label_print(frm, cdt, cdn) {
		let item = locals[cdt][cdn];
		
		if (!item.item_code) {
			frappe.msgprint(__("Please select an item first"));
			return;
		}

		// Get item details and barcode image
		frappe.call({
			method: "frappe.client.get",
			args: {
				doctype: "Item",
				name: item.item_code
			},
			callback: function(r) {
				if (r.message) {
					let item_doc = r.message;
					let barcode_image = null;
					let barcode_value = null;
					
					// Get barcode image from item
					if (item_doc.barcodes && item_doc.barcodes.length > 0) {
						for (let barcode_row of item_doc.barcodes) {
							if (barcode_row.custom_image) {
								barcode_image = barcode_row.custom_image;
								barcode_value = barcode_row.barcode;
								break;
							}
						}
					}

					if (!barcode_image) {
						frappe.msgprint(__('No barcode image found for this item.'));
						return;
					}

					// Get batch expiry if batch exists
					let expiry_date = "N/A";
					if (item.batch_no) {
						frappe.call({
							method: "frappe.client.get",
							args: {
								doctype: "Batch",
								name: item.batch_no
							},
							async: false,
							callback: function(batch_r) {
								if (batch_r.message && batch_r.message.expiry_date) {
									expiry_date = frappe.datetime.str_to_user(batch_r.message.expiry_date);
								}
							}
						});
					}

					// Format price
					let price = item.rate || item_doc.standard_rate || 0;
					let formatted_price = format_currency(price, frappe.defaults.get_default("currency") || "USD");

					// Open a new print window
					let printWindow = window.open('', '_blank');
					printWindow.document.open();
					printWindow.document.write(`
						<html>
						<head>
							<style>
								body {
									font-family: Arial, sans-serif;
									width: 2.299in;
									height: 1.5in;
									margin: 0;
									padding: 5px;
									box-sizing: border-box;
									display: flex;
									justify-content: center;
									align-items: center;
									text-align: center;
								}
								
								@page {
									size: 2.299in 1.5in;
									margin: 0;
								}

								.medication-label {
									width: 100%;
									height: 100%;
									border: 1px solid #000;
									padding: 5px;
									box-sizing: border-box;
									overflow: hidden;
									display: flex;
									flex-direction: column;
									justify-content: center;
									align-items: center;
									text-align: center;
								}

								.barcode-section {
									text-align: center;
									margin-bottom: 5px;
								}

								.barcode-section img {
									max-width: 100%;
									height: 35px;
									margin-bottom: 2px;
									image-rendering: crisp-edges;
								}

								.details-section {
									border-top: 1px solid #ccc;
									padding-top: 4px;
									margin-top: 4px;
									font-size: 7px;
									line-height: 1.1;
									text-align: center;
								}

								.item-name {
									font-weight: bold;
									font-size: 9px;
									margin-bottom: 2px;
									text-align: center;
									line-height: 1.1;
								}

								.detail-row {
									margin-bottom: 1px;
									line-height: 1.1;
								}

								img {
									max-width: 100%;
									height: auto;
								}
							</style>
						</head>
						<body>
							<div class="medication-label">
								<div class="barcode-section">
									<img src="${barcode_image}" alt="Barcode" />
								</div>
								
								<div class="details-section">
									<div class="item-name">${item.item_name || item.item_code}</div>
									<div class="detail-row">
										<strong>Strength:</strong> ${item_doc.custom_strength || "N/A"}
									</div>
									<div class="detail-row">
										<strong>Form:</strong> ${item_doc.custom_pharmaceutical_form || "N/A"}
									</div>
									<div class="detail-row">
										<strong>Price:</strong> ${formatted_price}
									</div>
									<div class="detail-row">
										<strong>Batch:</strong> ${item.batch_no || "N/A"}
									</div>
									<div class="detail-row">
										<strong>Expiry:</strong> ${expiry_date}
									</div>
								</div>
							</div>
							<script>
								window.onload = function() {
									window.print();
									window.onafterprint = function() {
										window.close();
									};
								};
							</script>
						</body>
						</html>
					`);
					printWindow.document.close();
				}
			}
		});
	}
});
