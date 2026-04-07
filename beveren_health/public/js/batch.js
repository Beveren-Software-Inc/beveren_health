// Copyright (c) 2026, Beveren Software and contributors
// For license information, please see license.txt

const BATCH_LABEL_CSS = `
	body { font-family: Arial, sans-serif; margin: 0; padding: 0; box-sizing: border-box; }
	@page { size: 2.299in 1.5in; margin: 0; }
	.label-page { width: 2.299in; height: 1.5in; padding: 5px; box-sizing: border-box; page-break-after: always; }
	.label-page:last-child { page-break-after: auto; }
	.medication-label { width: 100%; height: 100%; border: 1px solid #000; padding: 5px; box-sizing: border-box; overflow: hidden; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; }
	.barcode-section { text-align: center; margin-bottom: 2px;}
	.barcode-section img { max-width: 100%; height: 70px; margin-bottom: 1px; image-rendering: crisp-edges; }
	.details-section { padding-top: 1px; font-size: 7px; line-height: 1.1; text-align: center; width: 100%; background:red}
	.detail-row { margin-bottom: 1px; line-height: 1.1; }
	.item-name-line { font-family: Georgia, 'Times New Roman', serif; font-size: 8px; font-weight: bold; margin-bottom: 2px; }
	.price-row { font-size: 9px; }
	.price-value { font-weight: 900; font-size: 9px; }
	img { max-width: 100%; height: auto; }
`;


function build_batch_label_html(data, cost_center) {
	const barcode_number = (data.barcode_value != null && data.barcode_value !== "") ? data.barcode_value : "N/A";
	const item_code = data.item_code || "N/A";
	const item_name_line_val = data.item_name_line || "N/A";
	const standard_selling_price = data.standard_selling_price != null ? data.standard_selling_price : "N/A";
	const batch_number = data.batch_no || "N/A";
	const expiry_date = data.expiry_date != null ? data.expiry_date : "N/A";
	const branch = cost_center || "N/A";
	return `
		<div class="medication-label">
			<div class="details-section" style="border-top: none; padding-top: 0; margin-top: 2; margin-bottom: 1px;">
				<div class="detail-row"><strong>${branch}</strong> </div>
			</div>
			<div class="barcode-section">
				<img src="${data.barcode_image}" alt="Barcode" />
			</div>
			<div class="details-section">
				
				<div class="detail-row"><span> ${item_code} - </span><span class="item-name-line">${item_name_line_val}</span></div>
				<div class="detail-row"><strong>Price:</strong> <span class="price-value">${standard_selling_price}</span></div>
				<div class="detail-row"><strong>Batch No:</strong> ${batch_number}</div>
				<div class="detail-row"><strong>Expiry Date:</strong> ${expiry_date}</div>
			</div>
		</div>
	`;
}

frappe.ui.form.on("Batch", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Label Print"), function() {
				const batch_qty = flt(frm.doc.batch_qty, 0);
				const default_qty = batch_qty > 0 ? batch_qty : 1;

				const d = new frappe.ui.Dialog({
					title: __("Print Labels"),
					fields: [
						{
							fieldname: "num_labels",
							fieldtype: "Int",
							label: __("Number of Labels"),
							default: default_qty,
							reqd: 1,
							description: __("Default: batch quantity or 1"),
						},
						{
							fieldname: "cost_center",
							fieldtype: "Link",
							label: __("Branch (Cost Center)"),
							options: "Cost Center",
							description: __("Shown as Branch on the label"),
						},
					],
					primary_action_label: __("Print"),
					primary_action(values) {
						d.hide();
						const num = Math.max(1, parseInt(values.num_labels, 10) || 1);
						const cost_center = values.cost_center || "";

						// Fetch the custom_cr_no from Cost Center if selected
						let branch_display = cost_center;
						if (cost_center) {
							frappe.call({
								method: "frappe.client.get",
								args: {
									doctype: "Cost Center",
									name: cost_center,
								},
								async: false, // Use sync call to get the value before proceeding
								callback(cc_response) {
									if (cc_response.message) {
										console.log("Cost Center details:", cc_response.message);
										const raw_name = cc_response.message.custom_cr_name || cost_center;
										branch_display = raw_name
										
									}
								},
							});
						}

						frappe.call({
							method: "beveren_health.beveren_health.utils.label_printing.get_label_data_for_batch",
							args: { batch_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Loading label data..."),
							callback(r) {
								if (!r.message) {
									frappe.msgprint(__("Could not load label data for this batch."));
									return;
								}
								const data = r.message;
								if (!data.barcode_image) {
									frappe.msgprint(__("No barcode image found for Item {0}. Generate barcode from Item or Item Group.", [data.item_code]));
									return;
								}

								const labels_html = [];
								for (let i = 0; i < num; i++) {
									labels_html.push(
										'<div class="label-page">' +
										build_batch_label_html(data, branch_display) +
										"</div>"
									);
								}

								const w = window.open("", "_blank");
								w.document.write(
									"<html><head><style>" + BATCH_LABEL_CSS + "</style></head><body>" +
									labels_html.join("") +
									'<script>window.onload=function(){window.print();window.onafterprint=function(){window.close();}};<\/script></body></html>'
								);
								w.document.close();
							},
						});
					},
				});

				d.show();
			}, __("Actions"));
		}
		// frm.add_custom_button(__('Generate Barcode Image for All Batches'), function() {
		// 	frappe.call({
		// 		method: 'beveren_health.beveren_health.utils.batch.generate_barcode_for_existing_batches',
		// 		freeze: true,
		// 		freeze_message: __('Generating barcodes for existing batches...'),
		// 		callback: function(r) {
		// 			const msg = (r && r.message) ? r.message : __('Barcode generation job completed.');
		// 			frappe.msgprint(msg);
		// 		}
		// 	});
		// }, __("Actions"));

		// frm.add_custom_button(__('Generate Barcode for This Batch'), function() {
		// 	frappe.call({
		// 		method: 'beveren_health.beveren_health.utils.batch.generate_barcode_image_for_batch',
		// 		args: { batch_name: frm.doc.name },
		// 		freeze: true,
		// 		freeze_message: __('Generating barcode for this batch...'),
		// 		callback: function() {
		// 			frm.reload_doc();
		// 			frappe.show_alert({
		// 				message: __('Barcode generated for this batch'),
		// 				indicator: 'green'
		// 			});
		// 		}
		// 	});
		// }, __("Actions"));
	},
	
});