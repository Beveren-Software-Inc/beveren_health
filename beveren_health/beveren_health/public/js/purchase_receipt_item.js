// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

const LABEL_CSS = `
	body { font-family: Arial, sans-serif; margin: 0; padding: 0; box-sizing: border-box; }
	@page { size: 2.299in 1.5in; margin: 0; }
	.label-page { width: 2.299in; height: 1.5in; padding: 5px; box-sizing: border-box; page-break-after: always; }
	.label-page:last-child { page-break-after: auto; }
	.medication-label { width: 100%; height: 100%; border: 1px solid #000; padding: 5px; box-sizing: border-box; overflow: hidden; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; }
	.barcode-section { text-align: center; margin-bottom: 5px; }
	.barcode-section img { max-width: 100%; height: 35px; margin-bottom: 2px; image-rendering: crisp-edges; }
	.details-section { border-top: 1px solid #ccc; padding-top: 4px; margin-top: 4px; font-size: 7px; line-height: 1.1; text-align: center; }
	.detail-row { margin-bottom: 1px; line-height: 1.1; }
	.item-name-line { font-weight: bold; font-size: 9px; }
	img { max-width: 100%; height: auto; }
`;

function item_name_line(item_doc, batch_uom) {
	const uom = (batch_uom || item_doc.stock_uom || "").trim();
	const parts = [
		(item_doc.item_name || item_doc.name || "").trim(),
		(item_doc.custom_strength || "").trim(),
		(item_doc.custom_pharmaceutical_form || "").trim(),
		uom,
		(item_doc.custom_number_of_pack != null && item_doc.custom_number_of_pack !== "" ? String(item_doc.custom_number_of_pack) : "").trim()
	].filter(Boolean);
	return parts.length ? parts.join(" ") : "N/A";
}

function build_label_html(data) {
	const barcode_number = (data.barcode_value != null && data.barcode_value !== "") ? data.barcode_value : "N/A";
	const item_code = data.item_code || "N/A";
	const item_name_line_val = data.item_name_line || item_name_line(data.item_doc || {});
	const standard_selling_price = data.standard_selling_price != null ? data.standard_selling_price : "N/A";
	const batch_number = (data.batch_no_display != null && data.batch_no_display !== "") ? data.batch_no_display : "N/A";
	const expiry_date = data.expiry_date != null ? data.expiry_date : "N/A";
	return `
		<div class="medication-label">
			<div class="barcode-section">
				<img src="${data.barcode_image}" alt="Barcode" />
			</div>
			<div class="details-section">
				<div class="detail-row barcode-number">${barcode_number}</div>
				<div class="detail-row"><strong>Item Code:</strong> ${item_code}</div>
				<div class="detail-row item-name-line">${item_name_line_val}</div>
				<div class="detail-row"><strong>Item Standard Selling Price:</strong> ${standard_selling_price}</div>
				<div class="detail-row"><strong>Batch Number:</strong> ${batch_number}</div>
				<div class="detail-row"><strong>Expiry Date:</strong> ${expiry_date}</div>
			</div>
		</div>
	`;
}

function resolve_batch_and_expiry(item_row, item_doc, done) {
	let batch_no_display = item_row.batch_no || null;
	let expiry_date = "N/A";
	let batch_uom = null;

	if (item_row.batch_no) {
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "Batch", name: item_row.batch_no },
			callback: function(batch_r) {
				if (batch_r.message && batch_r.message.expiry_date) {
					expiry_date = frappe.datetime.str_to_user(batch_r.message.expiry_date);
				}
				batch_uom = (batch_r.message && batch_r.message.uom) || null;
				done({ batch_no_display: item_row.batch_no, expiry_date, batch_uom });
			}
		});
	} else if (item_row.serial_and_batch_bundle) {
		frappe.call({
			method: "beveren_health.beveren_health.utils.label_printing.get_batch_and_expiry_from_bundle",
			args: { serial_and_batch_bundle: item_row.serial_and_batch_bundle },
			callback: function(bundle_r) {
				if (bundle_r.message && bundle_r.message.batch_no) {
					batch_no_display = bundle_r.message.batch_no;
					if (bundle_r.message.expiry_date) {
						expiry_date = bundle_r.message.expiry_date;
					}
					batch_uom = bundle_r.message.uom || null;
				}
				done({ batch_no_display: batch_no_display || null, expiry_date, batch_uom });
			}
		});
	} else {
		done({ batch_no_display: null, expiry_date, batch_uom: null });
	}
}

function fetch_label_data_for_row(item_row) {
	return new Promise((resolve) => {
		frappe.call({
			method: "frappe.client.get",
			args: { doctype: "Item", name: item_row.item_code },
			callback: function(r) {
				if (!r.message) {
					resolve(null);
					return;
				}
				let item_doc = r.message;
				let barcode_image = null;
				let barcode_value = "";
				if (item_doc.barcodes && item_doc.barcodes.length > 0) {
					for (let b of item_doc.barcodes) {
						if (b.custom_image) {
							barcode_image = b.custom_image;
							barcode_value = b.barcode || "";
							break;
						}
					}
				}
				if (!barcode_image) {
					resolve(null);
					return;
				}
				let standard_rate = item_doc.standard_rate || 0;
				let standard_selling_price = format_currency(standard_rate, frappe.defaults.get_default("currency") || "USD");

				resolve_batch_and_expiry(item_row, item_doc, function(batch_info) {
					resolve({
						item_row,
						item_doc,
						barcode_image,
						barcode_value,
						item_code: item_doc.name || item_row.item_code,
						item_name_line: item_name_line(item_doc, batch_info.batch_uom),
						standard_selling_price,
						expiry_date: batch_info.expiry_date,
						batch_no_display: batch_info.batch_no_display
					});
				});
			}
		});
	});
}

// frappe.ui.form.on("Purchase Receipt", {
// 	refresh(frm) {
// 		frm.add_custom_button(__("Label Print"), function() {
// 			let items = (frm.doc.items || []).filter(function(row) { return row.item_code; });
// 			if (!items.length) {
// 				frappe.msgprint(__("No items to print labels for."));
// 				return;
// 			}
// 			frappe.dom.freeze(__("Loading label data…"));
// 			let promises = items.map(function(item_row) { return fetch_label_data_for_row(item_row); });
// 			Promise.all(promises).then(function(results) {
// 				frappe.dom.unfreeze();
// 				let labels_html = [];
// 				let skipped = 0;
// 				results.forEach(function(data) {
// 					if (!data) {
// 						skipped++;
// 						return;
// 					}
// 					labels_html.push(
// 						'<div class="label-page">' +
// 						build_label_html(data.item_row, data.item_doc, data.barcode_image, data.expiry_date, data.formatted_price) +
// 						'</div>'
// 					);
// 				});
// 				if (!labels_html.length) {
// 					frappe.msgprint(__("No items with barcode image found."));
// 					return;
// 				}
// 				if (skipped) {
// 					frappe.show_alert({ message: __("{0} item(s) skipped (no barcode).", [skipped]), indicator: "orange" });
// 				}
// 				let print_window = window.open("", "_blank");
// 				print_window.document.open();
// 				print_window.document.write(
// 					"<html><head><style>" + LABEL_CSS + "</style></head><body>" +
// 					labels_html.join("") +
// 					"<script>window.onload = function() { window.print(); window.onafterprint = function() { window.close(); }; };<\/script></body></html>"
// 				);
// 				print_window.document.close();
// 			});
// 		});
// 	}
// });

// --------------------------------------------------
// MAIN PRINT BUTTON
// --------------------------------------------------
frappe.ui.form.on("Purchase Receipt", {

	refresh(frm) {

		frm.add_custom_button(__("Label Print"), function() {

			let items = (frm.doc.items || []).filter(r => r.item_code);

			if (!items.length) {
				frappe.msgprint(__("No items to print."));
				return;
			}

			frappe.dom.freeze(__("Preparing labels..."));

			let promises = items.map(r => fetch_label_data_for_row(r));

			Promise.all(promises).then(results => {

				frappe.dom.unfreeze();

				let labels_html = [];
				let skipped = 0;

				results.forEach(data => {

					if (!data) {
						skipped++;
						return;
					}

					// ✅ PRINT PER QUANTITY
					let qty = Math.round(flt(data.item_row.qty) || 1);

					for (let i = 0; i < qty; i++) {
						labels_html.push(
							'<div class="label-page">' +
							build_label_html(data) +
							'</div>'
						);
					}
				});

				if (!labels_html.length) {
					frappe.msgprint(__("No printable labels."));
					return;
				}

				if (skipped) {
					frappe.show_alert({
						message: __("{0} item(s) skipped (no barcode).", [skipped]),
						indicator: "orange"
					});
				}

				let w = window.open("", "_blank");

				w.document.write(
					"<html><head><style>" + LABEL_CSS + "</style></head><body>" +
					labels_html.join("") +
					"<script>window.onload=function(){window.print();window.onafterprint=function(){window.close();}}<\/script>" +
					"</body></html>"
				);

				w.document.close();
			});
		});
	}
});

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

					// Resolve batch and expiry: from batch_no or from Serial and Batch Bundle
					let batch_no_display = item.batch_no || null;
					let expiry_date = "N/A";
					let batch_uom = null;

					function render_single_label() {
						const barcode_number = (barcode_value != null && barcode_value !== "") ? barcode_value : "N/A";
						const item_code_val = item_doc.name || item.item_code || "N/A";
						const item_name_line_val = item_name_line(item_doc, batch_uom);
						const standard_selling_price = format_currency(item_doc.standard_rate || 0, frappe.defaults.get_default("currency") || "USD");
						const batch_label = batch_no_display != null && batch_no_display !== "" ? batch_no_display : "N/A";

						let printWindow = window.open("", "_blank");
						printWindow.document.open();
						printWindow.document.write(`
						<html>
						<head>
							<style>
								body { font-family: Arial, sans-serif; width: 2.299in; height: 1.5in; margin: 0; padding: 5px; box-sizing: border-box; display: flex; justify-content: center; align-items: center; text-align: center; }
								@page { size: 2.299in 1.5in; margin: 0; }
								.medication-label { width: 100%; height: 100%; border: 1px solid #000; padding: 5px; box-sizing: border-box; overflow: hidden; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; }
								.barcode-section { text-align: center; margin-bottom: 5px; }
								.barcode-section img { max-width: 100%; height: 35px; margin-bottom: 2px; image-rendering: crisp-edges; }
								.details-section { border-top: 1px solid #ccc; padding-top: 4px; margin-top: 4px; font-size: 7px; line-height: 1.1; text-align: center; }
								.detail-row { margin-bottom: 1px; line-height: 1.1; }
								img { max-width: 100%; height: auto; }
							</style>
						</head>
						<body>
							<div class="medication-label">
								<div class="barcode-section">
									<img src="${barcode_image}" alt="Barcode" />
								</div>
								<div class="details-section">
									<div class="detail-row barcode-number">${barcode_number}</div>
									<div class="detail-row"><strong>Item Code:</strong> ${item_code_val}</div>
									<div class="detail-row item-name-line">${item_name_line_val}</div>
									<div class="detail-row"><strong>Item Standard Selling Price:</strong> ${standard_selling_price}</div>
									<div class="detail-row"><strong>Batch Number:</strong> ${batch_label}</div>
									<div class="detail-row"><strong>Expiry Date:</strong> ${expiry_date}</div>
								</div>
							</div>
							<script>window.onload=function(){window.print();window.onafterprint=function(){window.close();}};<\/script>
						</body>
						</html>
						`);
						printWindow.document.close();
					}

					if (item.batch_no) {
						frappe.call({
							method: "frappe.client.get",
							args: { doctype: "Batch", name: item.batch_no },
							callback: function(batch_r) {
								if (batch_r.message && batch_r.message.expiry_date) {
									expiry_date = frappe.datetime.str_to_user(batch_r.message.expiry_date);
								}
								batch_uom = (batch_r.message && batch_r.message.uom) || null;
								render_single_label();
							}
						});
					} else if (item.serial_and_batch_bundle) {
						frappe.call({
							method: "beveren_health.beveren_health.utils.label_printing.get_batch_and_expiry_from_bundle",
							args: { serial_and_batch_bundle: item.serial_and_batch_bundle },
							callback: function(bundle_r) {
								if (bundle_r.message && bundle_r.message.batch_no) {
									batch_no_display = bundle_r.message.batch_no;
									if (bundle_r.message.expiry_date) expiry_date = bundle_r.message.expiry_date;
									batch_uom = bundle_r.message.uom || null;
								}
								render_single_label();
							}
						});
					} else {
						render_single_label();
					}
				}
			}
		});
	}
});
