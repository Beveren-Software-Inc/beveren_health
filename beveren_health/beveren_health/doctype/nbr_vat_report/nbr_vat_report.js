frappe.ui.form.on('NBR VAT Report', {
	onload: function(frm) {
		frm.report_state = {
			active_view: 'Summary', // 'Summary' or 'Detailed'
			level: 1,      // 1: Form, 2: Category, 3: Invoices
			row_id: null,
			category: null,
			collapsed_groups: [] // Track collapsed group names
		};
	},

	refresh: function(frm) {
		// Permanently hide the right-side layout section to make the report full width
		frm.layout.show_sidebar = false;
		$('.layout-side-section').hide();
		$('.layout-main-section').removeClass('col-lg-10').addClass('col-lg-12');

		// Hide section headers to make the dashboard minimalistic
		$('div[data-fieldname="filters_section"] .section-head').hide();
		$('div[data-fieldname="report_section"] .section-head').hide();
		setTimeout(() => {
			$('div[data-fieldname="filters_section"] .section-head').hide();
			$('div[data-fieldname="report_section"] .section-head').hide();
		}, 100);

		// Set primary action button to "Generate" instead of "Save"
		frm.page.set_primary_action(__('Generate'), function() {
			frm.trigger('refresh_report');
		});

		// Set secondary action button to "Download Excel" on Navbar
		frm.page.set_secondary_action(__('Download Excel'), function() {
			let company = frm.doc.company;
			let from_date = frm.doc.from_date;
			let to_date = frm.doc.to_date;
			let tax_id = frm.doc.tax_id || '';
			if (!company || !from_date || !to_date) {
				frappe.msgprint(__('Please select Company, From Date, and To Date.'));
				return;
			}
			let url = `/api/method/beveren_health.beveren_health.utils.nbr_vat_api.download_vat_excel?company=${encodeURIComponent(company)}&from_date=${from_date}&to_date=${to_date}&tax_id=${encodeURIComponent(tax_id)}`;
			window.open(url, '_blank');
		});

		// Auto fetch VAT numbers list on refresh
		if (frm.doc.company) {
			frappe.call({
				method: 'beveren_health.beveren_health.utils.nbr_vat_api.get_company_vat_numbers',
				args: { company: frm.doc.company },
				callback: function(r) {
					let vat_list = r.message || [];
					frm.set_df_property('tax_id', 'options', [''].concat(vat_list));
					
					// Set value without marking document as dirty
					if (vat_list.length > 0 && !frm.doc.tax_id) {
						frm.doc.tax_id = vat_list[0];
						frm.refresh_field('tax_id');
					}
				}
			});
		}

		frm.trigger('refresh_report');
	},

	company: function(frm) {
		if (frm.doc.company) {
			frappe.call({
				method: 'beveren_health.beveren_health.utils.nbr_vat_api.get_company_vat_numbers',
				args: { company: frm.doc.company },
				callback: function(r) {
					let vat_list = r.message || [];
					frm.set_df_property('tax_id', 'options', [''].concat(vat_list));
					
					// Set value without marking document as dirty
					frm.doc.tax_id = vat_list.length > 0 ? vat_list[0] : '';
					frm.refresh_field('tax_id');
					frm.trigger('refresh_report');
				}
			});
		} else {
			frm.set_df_property('tax_id', 'options', ['']);
			frm.doc.tax_id = '';
			frm.refresh_field('tax_id');
			frm.trigger('refresh_report');
		}
	},
	tax_id: function(frm) {
		frm.trigger('refresh_report');
	},
	from_date: function(frm) { frm.trigger('refresh_report'); },
	to_date: function(frm) { frm.trigger('refresh_report'); },

	refresh_report: function(frm) {
		if (!frm.doc.company || !frm.doc.from_date || !frm.doc.to_date) {
			frm.set_df_property('report_html', 'options', '<div class="alert alert-info">' + __('Please select Company, From Date, and To Date to generate the report.') + '</div>');
			return;
		}

		// Fetch summary data & detailed list
		frappe.run_serially([
			() => {
				return frappe.call({
					method: 'beveren_health.beveren_health.utils.nbr_vat_api.get_vat_return_summary',
					args: {
						company: frm.doc.company,
						from_date: frm.doc.from_date,
						to_date: frm.doc.to_date,
						tax_id: frm.doc.tax_id || ''
					},
					freeze: true,
					callback: function(r) {
						frm.summary_data = r.message;
					}
				});
			},
			() => {
				return frappe.call({
					method: 'beveren_health.beveren_health.utils.nbr_vat_api.get_all_contributing_invoices',
					args: {
						company: frm.doc.company,
						from_date: frm.doc.from_date,
						to_date: frm.doc.to_date,
						tax_id: frm.doc.tax_id || ''
					},
					freeze: true,
					callback: function(r) {
						frm.detailed_list = r.message;
					}
				});
			},
			() => {
				frm.trigger('render_report');
			}
		]);
	},

	render_report: function(frm) {
		if (!frm.summary_data) return;

		let html = '';

		// Inject CSS Styles directly to guarantee they load and apply perfectly
		html += `
			<style>
				.bahrain-vat-container {
					padding: 0;
					font-family: var(--font-family);
				}
				.vat-summary-row {
					display: flex;
					justify-content: center;
					gap: 16px;
					margin-bottom: 12px;
				}
				.vat-summary-item {
					border: none;
					border-bottom: 3px solid var(--border-color, #e2e8f0);
					background-color: var(--card-bg, #ffffff);
					padding: 10px 16px;
					text-align: center;
					flex: 1;
					max-width: 260px;
					border-radius: 0px !important;
				}
				.vat-summary-label {
					font-size: 0.75rem;
					color: var(--text-muted, #718096);
					margin-bottom: 2px;
				}
				.vat-summary-value {
					font-size: 1.2rem;
					font-weight: bold;
					color: var(--text-color, #1a202c);
				}
				.vat-view-header-row {
					display: flex;
					justify-content: space-between;
					align-items: center;
					margin-bottom: 0px;
					padding-bottom: 8px;
					border-bottom: none;
				}
				.vat-breadcrumb {
					display: flex;
					align-items: center;
					font-size: 0.9rem;
				}
				.vat-breadcrumb-item {
					color: var(--text-muted, #718096);
					text-decoration: none;
					cursor: pointer;
				}
				.vat-breadcrumb-item.active {
					color: var(--primary-color, #3182ce);
					font-weight: 600;
				}
				.vat-breadcrumb-separator {
					margin: 0 8px;
					color: var(--text-muted, #a0aec0);
				}
				.vat-section-title-row {
					display: flex;
					justify-content: flex-end;
					align-items: center;
					padding-bottom: 4px;
					margin-top: 0px;
					margin-bottom: 6px;
				}
				.vat-table {
					margin-top: 0px !important;
					margin-bottom: 12px;
				}
				.vat-table th, .vat-table td {
					padding: 6px 10px !important;
					font-size: 0.85rem !important;
				}
				.vat-table tr.clickable-row {
					cursor: pointer;
				}
				.vat-table tr.clickable-row:hover td {
					color: var(--primary-color, #3182ce) !important;
				}
				.vat-table tr.parent-node {
					font-weight: bold;
					background-color: var(--table-bg-hover, #f8f9fa) !important;
					cursor: pointer;
				}
				.vat-table tr.parent-node i {
					margin-right: 8px;
					color: var(--text-muted, #718096);
					transition: transform 0.2s;
				}
				.vat-table tr.child-node td.indent-col {
					padding-left: 32px !important;
				}
				.vat-table tr.collapsed i {
					transform: rotate(-90deg);
				}
				.vat-amount-col {
					text-align: right !important;
					font-variant-numeric: tabular-nums;
				}
				.vat-indicator-pill {
					display: inline-block;
					padding: 2px 8px;
					font-size: 0.75rem;
					font-weight: 600;
					border-radius: 9999px;
					text-transform: uppercase;
				}
				.vat-indicator-pill.b2b {
					background-color: #ebf8ff;
					color: #2b6cb0;
				}
				.vat-indicator-pill.b2c {
					background-color: #f7fafc;
					color: #4a5568;
				}
				.vat-table-actions {
					display: flex;
					gap: 8px;
				}
				.vat-footer-toolbar {
					display: flex;
					justify-content: space-between;
					align-items: center;
					padding-top: 12px;
					font-size: 0.85rem;
					color: var(--text-muted, #718096);
				}
				.vat-footer-buttons {
					display: flex;
					gap: 8px;
				}
			</style>
		`;

		html += '<div class="bahrain-vat-container">';

		// RENDER 1: Replicating GSTR-1 Net Output GST Liability layout (as individual rectangular cards with border, 0px radius and gap)
		let total_sales_vat = frm.summary_data.rows["7"].vat || 0.0;
		let total_purch_vat = frm.summary_data.rows["14"].vat || 0.0;
		let net_vat_due = frm.summary_data.row_18_vat || 0.0;

		html += `
			<div class="vat-summary-row">
				<div class="vat-summary-item" style="border-bottom: 3px solid var(--border-color, #e2e8f0);">
					<div class="vat-summary-label">${__("Sales VAT Amount")}</div>
					<div class="vat-summary-value">${frm.events.format_bhd(total_sales_vat)}</div>
				</div>
				<div class="vat-summary-item" style="border-bottom: 3px solid var(--border-color, #e2e8f0);">
					<div class="vat-summary-label">${__("Purchase VAT Amount")}</div>
					<div class="vat-summary-value">${frm.events.format_bhd(total_purch_vat)}</div>
				</div>
				<div class="vat-summary-item" style="border-bottom: 3px solid ${net_vat_due >= 0 ? '#48bb78' : '#e53e3e'};">
					<div class="vat-summary-label">${__("Net VAT Due / (Reclaimed)")}</div>
					<div class="vat-summary-value" style="color: ${net_vat_due >= 0 ? '#2f855a' : '#c53030'};">
						${frm.events.format_bhd(net_vat_due)}
					</div>
				</div>
			</div>
		`;

		// RENDER 2: View Header Row (Breadcrumbs on the left, Summary/Detailed toggle inline on the right)
		let summary_active = frm.report_state.active_view === 'Summary' ? 'active btn-info' : 'btn-default';
		let detailed_active = frm.report_state.active_view === 'Detailed' ? 'active btn-info' : 'btn-default';

		html += `
			<div class="vat-view-header-row">
				<div>
					${frm.report_state.active_view === 'Summary' ? frm.events.get_breadcrumbs_html(frm) : '<span class="vat-breadcrumb-item active">' + __('All Contributing Transactions (Detailed View)') + '</span>'}
				</div>
				<div class="btn-group" role="group">
					<button type="button" class="btn btn-xs btn-summary-toggle ${summary_active}">${__("Summary")}</button>
					<button type="button" class="btn btn-xs btn-detailed-toggle ${detailed_active}">${__("Detailed")}</button>
				</div>
			</div>
		`;

		// RENDER 3: View Content
		if (frm.report_state.active_view === 'Summary') {
			if (frm.report_state.level === 1) {
				html += frm.events.get_form_html(frm);
			} else if (frm.report_state.level === 2) {
				html += frm.events.get_category_html(frm);
			} else if (frm.report_state.level === 3) {
				html += frm.events.get_invoices_html(frm);
			}
		} else {
			html += frm.events.get_detailed_list_html(frm);
		}

		html += '</div>';

		frm.fields_dict.report_html.html(html);
		frm.trigger('bind_report_events');
	},

	format_bhd: function(value) {
		let val = flt(value);
		let formatted = Math.abs(val).toLocaleString('en-US', {
			minimumFractionDigits: 3,
			maximumFractionDigits: 3
		});
		let sign = val < 0 ? '-' : '';
		// dir="ltr" with unicode-bidi isolate ensures no RTL character mixing breaks digits ordering
		return `<bdi dir="ltr" style="unicode-bidi: isolate; display: inline-block; white-space: nowrap;">${sign}${formatted} د.ب</bdi>`;
	},

	format_count: function(value) {
		let val = flt(value);
		return val.toLocaleString('en-US', {
			minimumFractionDigits: 3,
			maximumFractionDigits: 3
		});
	},

	get_breadcrumbs_html: function(frm) {
		let html = '<div class="vat-breadcrumb">';
		if (frm.report_state.level === 1) {
			html += '<span class="vat-breadcrumb-item active">' + __('Summary of Books') + '</span>';
		} else {
			html += '<a class="vat-breadcrumb-item btn-back-level1">' + __('Summary of Books') + '</a>';
			html += '<span class="vat-breadcrumb-separator">/</span>';
			
			let row_desc = frm.summary_data.rows[frm.report_state.row_id].desc;
			if (frm.report_state.level === 2) {
				html += '<span class="vat-breadcrumb-item active">' + row_desc + '</span>';
			} else {
				html += '<a class="vat-breadcrumb-item btn-back-level2">' + row_desc + '</a>';
				html += '<span class="vat-breadcrumb-separator">/</span>';
				html += '<span class="vat-breadcrumb-item active">' + frm.report_state.category + '</span>';
			}
		}
		html += '</div>';
		return html;
	},

	get_form_html: function(frm) {
		let rows = frm.summary_data.rows;
		let net_vat_due = frm.summary_data.row_18_vat || 0.0;
		let html = '<div>';
		
		// No action row since Download Excel is in the header navbar

		const row_meta = {
			"1a": { "no": "1(a)", "desc": "Standard Rated Sales at 10%" },
			"1b": { "no": "1(b)", "desc": "Standard Rated Sales at 5%" },
			"2": { "no": "2", "desc": "Sales to Registered VAT Payers in Other GCC States" },
			"3": { "no": "3", "desc": "Sales Subject to Domestic Reverse Charge Mechanism" },
			"4": { "no": "4", "desc": "Zero-Rated Domestic Sales" },
			"5": { "no": "5", "desc": "Exports" },
			"6": { "no": "6", "desc": "Exempt Sales" },
			"8a": { "no": "8(a)", "desc": "Standard Rated Domestic Purchases at 10%" },
			"8b": { "no": "8(b)", "desc": "Standard Rated Domestic Purchases at 5%" },
			"9a": { "no": "9(a)", "desc": "Imports Subject to VAT Paid at Customs at 10%" },
			"9b": { "no": "9(b)", "desc": "Imports Subject to VAT Paid at Customs at 5%" },
			"10": { "no": "10", "desc": "Imports Subject to Deferral at Customs" },
			"11a": { "no": "11(a)", "desc": "Imports Subject to VAT Accounted for Through Reverse Charge Mechanism at 10%" },
			"11b": { "no": "11(b)", "desc": "Imports Subject to VAT Accounted for Through Reverse Charge Mechanism at 5%" },
			"12": { "no": "12", "desc": "Purchases Subject to Domestic Reverse Charge Mechanism" },
			"13": { "no": "13", "desc": "Purchases from Non-Registered Suppliers, Zero-Rated/Exempt Purchases" }
		};

		// Hierarchical Tree Table using standard Frappe classes (No filter row)
		html += '<table class="table table-bordered table-hover list-table vat-table">';
		html += `
			<thead>
				<tr>
					<th class="text-center" style="width: 55px;">${__("No.")}</th>
					<th>${__("Description")}</th>
					<th class="vat-amount-col">${__("Total Docs")}</th>
					<th class="vat-amount-col">${__("Taxable Value")}</th>
					<th class="vat-amount-col">${__("Adjustment")}</th>
					<th class="vat-amount-col">${__("VAT Amount")}</th>
				</tr>
			</thead>
		`;
		html += '<tbody>';

		let row_idx = 1;

		// 1. Sales Parent Row
		let is_sales_collapsed = frm.report_state.collapsed_groups.indexOf('sales') !== -1;
		let sales_style = is_sales_collapsed ? 'style="display:none;"' : '';
		let sales_class = is_sales_collapsed ? 'collapsed' : '';
		
		html += `
			<tr class="parent-node ${sales_class}" data-group="sales">
				<td class="text-center" style="font-weight: bold;">${row_idx++}</td>
				<td style="font-weight: bold;"><i class="fa fa-chevron-down"></i> ${__("VAT on Sales (Output VAT)")}</td>
				<td class="vat-amount-col" style="font-weight: bold;">${frm.events.format_count(rows["7"].count)}</td>
				<td class="vat-amount-col" style="font-weight: bold;">${frm.events.format_bhd(rows["7"].amount)}</td>
				<td class="vat-amount-col" style="font-weight: bold;">${frm.events.format_bhd(rows["7"].adjustment)}</td>
				<td class="vat-amount-col" style="font-weight: bold;">${frm.events.format_bhd(rows["7"].vat)}</td>
			</tr>
		`;

		let sales_keys = ["1a", "1b", "2", "3", "4", "5", "6"];
		sales_keys.forEach(k => {
			let meta = row_meta[k];
			html += `
				<tr class="child-node clickable-row" data-parent-group="sales" data-row-id="${k}" ${sales_style}>
					<td class="text-center">${meta.no}</td>
					<td class="indent-col">${__(meta.desc)}</td>
					<td class="vat-amount-col">${frm.events.format_count(rows[k].count)}</td>
					<td class="vat-amount-col">${frm.events.format_bhd(rows[k].amount)}</td>
					<td class="vat-amount-col">${frm.events.format_bhd(rows[k].adjustment)}</td>
					<td class="vat-amount-col">${frm.events.format_bhd(rows[k].vat)}</td>
				</tr>
			`;
		});

		// 2. Purchases Parent Row
		let is_purch_collapsed = frm.report_state.collapsed_groups.indexOf('purch') !== -1;
		let purch_style = is_purch_collapsed ? 'style="display:none;"' : '';
		let purch_class = is_purch_collapsed ? 'collapsed' : '';

		html += `
			<tr class="parent-node ${purch_class}" data-group="purch">
				<td class="text-center" style="font-weight: bold;">${row_idx++}</td>
				<td style="font-weight: bold;"><i class="fa fa-chevron-down"></i> ${__("VAT on Purchases (Input VAT)")}</td>
				<td class="vat-amount-col" style="font-weight: bold;">${frm.events.format_count(rows["14"].count)}</td>
				<td class="vat-amount-col" style="font-weight: bold;">${frm.events.format_bhd(rows["14"].amount)}</td>
				<td class="vat-amount-col" style="font-weight: bold;">${frm.events.format_bhd(rows["14"].adjustment)}</td>
				<td class="vat-amount-col" style="font-weight: bold;">${frm.events.format_bhd(rows["14"].vat)}</td>
			</tr>
		`;

		let purchase_keys = ["8a", "8b", "9a", "9b", "10", "11a", "11b", "12", "13"];
		purchase_keys.forEach(k => {
			let meta = row_meta[k];
			html += `
				<tr class="child-node clickable-row" data-parent-group="purch" data-row-id="${k}" ${purch_style}>
					<td class="text-center">${meta.no}</td>
					<td class="indent-col">${__(meta.desc)}</td>
					<td class="vat-amount-col">${frm.events.format_count(rows[k].count)}</td>
					<td class="vat-amount-col">${frm.events.format_bhd(rows[k].amount)}</td>
					<td class="vat-amount-col">${frm.events.format_bhd(rows[k].adjustment)}</td>
					<td class="vat-amount-col">${frm.events.format_bhd(rows[k].vat)}</td>
				</tr>
			`;
		});

		// 3. Net VAT Calculation Parent Row
		let is_net_collapsed = frm.report_state.collapsed_groups.indexOf('net') !== -1;
		let net_style = is_net_collapsed ? 'style="display:none;"' : '';
		let net_class = is_net_collapsed ? 'collapsed' : '';

		html += `
			<tr class="parent-node ${net_class}" data-group="net">
				<td class="text-center" style="font-weight: bold;">${row_idx++}</td>
				<td style="font-weight: bold;"><i class="fa fa-chevron-down"></i> ${__("Net VAT Calculation")}</td>
				<td class="vat-amount-col" style="font-weight: bold;">-</td>
				<td class="vat-amount-col" style="font-weight: bold;">-</td>
				<td class="vat-amount-col" style="font-weight: bold;">-</td>
				<td class="vat-amount-col" style="font-weight: bold; color: ${net_vat_due >= 0 ? '#2f855a' : '#c53030'}">
					${frm.events.format_bhd(net_vat_due)}
				</td>
			</tr>
		`;

		// Net VAT child lines (Rows 15, 16, 17, 18)
		html += `
			<tr class="child-node" data-parent-group="net" ${net_style}>
				<td class="text-center">15</td>
				<td class="indent-col">${__("Total VAT Due for Current Period")}</td>
				<td class="vat-amount-col">-</td>
				<td class="vat-amount-col">-</td>
				<td class="vat-amount-col">-</td>
				<td class="vat-amount-col">${frm.events.format_bhd(frm.summary_data.row_15_vat)}</td>
			</tr>
			<tr class="child-node" data-parent-group="net" ${net_style}>
				<td class="text-center">16</td>
				<td class="indent-col">${__("Corrections from Previous Period (between BHD \u00b15,000)")}</td>
				<td class="vat-amount-col">-</td>
				<td class="vat-amount-col">-</td>
				<td class="vat-amount-col">-</td>
				<td class="vat-amount-col">${frm.events.format_bhd(frm.summary_data.row_16_correction_amount)}</td>
			</tr>
			<tr class="child-node" data-parent-group="net" ${net_style}>
				<td class="text-center">17</td>
				<td class="indent-col">${__("VAT Credit Carried Forward from Previous Period(s)")}</td>
				<td class="vat-amount-col">-</td>
				<td class="vat-amount-col">-</td>
				<td class="vat-amount-col">-</td>
				<td class="vat-amount-col">${frm.events.format_bhd(frm.summary_data.row_17_credit_carried_forward)}</td>
			</tr>
			<tr class="child-node total-row" data-parent-group="net" ${net_style} style="background-color: #ebf8ff; color: #2b6cb0;">
				<td class="text-center">18</td>
				<td class="indent-col" style="font-weight: bold;">${__("Net VAT Due (or Reclaimed)")}</td>
				<td class="vat-amount-col" style="font-weight: bold;">-</td>
				<td class="vat-amount-col" style="font-weight: bold;">-</td>
				<td class="vat-amount-col" style="font-weight: bold;">-</td>
				<td class="vat-amount-col" style="font-weight: bold; font-size: 1.05rem;">${frm.events.format_bhd(net_vat_due)}</td>
			</tr>
		`;

		html += '</tbody></table>';

		// Expand All / Collapse All Footer buttons & Created Just Now
		html += `
			<div class="vat-footer-toolbar">
				<div class="vat-footer-buttons">
					<button class="btn btn-default btn-xs btn-expand-all-tree"><i class="fa fa-caret-down"></i> ${__("Expand All")}</button>
					<button class="btn btn-default btn-xs btn-collapse-all-tree"><i class="fa fa-caret-right"></i> ${__("Collapse All")}</button>
				</div>
				<div class="vat-timestamp-indicator">
					${__("Created Just Now")}
				</div>
			</div>
		</div>
		`;
		return html;
	},

	get_category_html: function(frm) {
		let row_id = frm.report_state.row_id;
		let breakup = frm.category_data;
		let html = '<div>';
		html += `
			<div class="vat-section-title-row">
				<div class="vat-section-title">${frm.events.get_breadcrumbs_html(frm)}</div>
			</div>
		`;
		html += '<table class="table table-bordered table-hover list-table vat-table">';
		html += '<thead><tr><th>' + __('Classification') + '</th><th class="vat-amount-col">' + __('Amount (BHD)') + '</th><th class="vat-amount-col">' + __('VAT Amount (BHD)') + '</th></tr></thead>';
		html += '<tbody>';
		
		if (["1a", "1b", "2", "3", "4", "5", "6", "8a", "8b", "12", "13"].indexOf(row_id) !== -1) {
			html += `<tr class="clickable-row category-row" data-category="B2B">`;
			html += `<td><span class="vat-indicator-pill b2b">B2B</span> ` + __('Registered / Business Transactions') + `</td>`;
			html += `<td class="vat-amount-col">${frm.events.format_bhd(breakup.b2b_amount)}</td>`;
			html += `<td class="vat-amount-col">${frm.events.format_bhd(breakup.b2b_vat)}</td>`;
			html += '</tr>';

			html += `<tr class="clickable-row category-row" data-category="B2C">`;
			html += `<td><span class="vat-indicator-pill b2c">B2C</span> ` + __('Unregistered / Consumer Transactions') + `</td>`;
			html += `<td class="vat-amount-col">${frm.events.format_bhd(breakup.b2c_amount)}</td>`;
			html += `<td class="vat-amount-col">${frm.events.format_bhd(breakup.b2c_vat)}</td>`;
			html += '</tr>';
		} else {
			html += `<tr class="clickable-row category-row" data-category="B2B">`;
			html += `<td>` + __('Import Purchases') + `</td>`;
			html += `<td class="vat-amount-col">${frm.events.format_bhd(breakup.b2b_amount)}</td>`;
			html += `<td class="vat-amount-col">${frm.events.format_bhd(breakup.b2b_vat)}</td>`;
			html += '</tr>';
		}

		html += '</tbody></table></div>';
		return html;
	},

	get_invoices_html: function(frm) {
		let list = frm.invoice_list || [];
		let html = '<div>';
		html += `
			<div class="vat-section-title-row">
				<div class="vat-section-title">${frm.events.get_breadcrumbs_html(frm)}</div>
			</div>
		`;
		
		if (list.length === 0) {
			html += '<p>' + __('No contributing documents found.') + '</p>';
		} else {
			html += '<table class="table table-bordered table-hover list-table vat-table">';
			html += '<thead><tr><th>' + __('Document No') + '</th><th>' + __('Party') + '</th><th>' + __('Posting Date') + '</th><th class="vat-amount-col">' + __('Taxable Value (BHD)') + '</th><th class="vat-amount-col">' + __('VAT Amount (BHD)') + '</th></tr></thead>';
			html += '<tbody>';
			
			list.forEach(inv => {
				html += '<tr>';
				html += `<td><a href="/app/${frappe.router.slug(inv.doctype)}/${inv.invoice_no}">${inv.invoice_no}</a></td>`;
				html += `<td>${inv.party}</td>`;
				html += `<td>${frappe.datetime.str_to_user(inv.date)}</td>`;
				html += `<td class="vat-amount-col">${frm.events.format_bhd(inv.taxable_value)}</td>`;
				html += `<td class="vat-amount-col">${frm.events.format_bhd(inv.vat_amount)}</td>`;
				html += '</tr>';
			});
			html += '</tbody></table>';
		}
		html += '</div>';
		return html;
	},

	get_detailed_list_html: function(frm) {
		let list = frm.detailed_list || [];
		let html = '<div>';
		html += `
			<div class="vat-section-title-row">
				<div class="vat-section-title"><span class="vat-breadcrumb-item active">${__("All Contributing Transactions (Detailed View)")}</span></div>
			</div>
		`;
		
		if (list.length === 0) {
			html += '<p>' + __('No contributing documents found.') + '</p>';
		} else {
			html += '<table class="table table-bordered table-hover list-table vat-table">';
			html += '<thead><tr><th>' + __('Document No') + '</th><th>' + __('Document Type') + '</th><th>' + __('Party') + '</th><th>' + __('Posting Date') + '</th><th>' + __('NBR Box') + '</th><th class="vat-amount-col">' + __('Taxable Value (BHD)') + '</th><th class="vat-amount-col">' + __('VAT Amount (BHD)') + '</th></tr></thead>';
			html += '<tbody>';
			
			list.forEach(inv => {
				html += '<tr>';
				html += `<td><a href="/app/${frappe.router.slug(inv.doctype)}/${inv.invoice_no}">${inv.invoice_no}</a></td>`;
				html += `<td>${inv.doctype}</td>`;
				html += `<td>${inv.party}</td>`;
				html += `<td>${frappe.datetime.str_to_user(inv.date)}</td>`;
				html += `<td><span class="label label-info" style="font-size:0.8rem; padding: 2px 6px;">Box ${inv.box}</span></td>`;
				html += `<td class="vat-amount-col">${frm.events.format_bhd(inv.taxable_value)}</td>`;
				html += `<td class="vat-amount-col">${frm.events.format_bhd(inv.vat_amount)}</td>`;
				html += '</tr>';
			});
			html += '</tbody></table>';
		}
		html += '</div>';
		return html;
	},

	bind_report_events: function(frm) {
		let $wrapper = $(frm.fields_dict.report_html.wrapper);

		// Unbind any previous delegated events to prevent duplicates
		$wrapper.off('click');

		// View toggles Summary vs Detailed (Delegated robustly)
		$wrapper.on('click', '.btn-summary-toggle', function() {
			frm.report_state.active_view = 'Summary';
			frm.report_state.level = 1;
			frm.report_state.row_id = null;
			frm.report_state.category = null;
			frm.trigger('refresh_report');
		});

		$wrapper.on('click', '.btn-detailed-toggle', function() {
			frm.report_state.active_view = 'Detailed';
			frm.trigger('refresh_report');
		});

		// Recompute & Excel export listeners in header (Delegated robustly)
		$wrapper.on('click', '.btn-recompute-data', function() {
			frm.trigger('refresh_report');
		});

		$wrapper.on('click', '.btn-export-excel', function() {
			let company = frm.doc.company;
			let from_date = frm.doc.from_date;
			let to_date = frm.doc.to_date;
			let tax_id = frm.doc.tax_id || '';
			let url = `/api/method/beveren_health.beveren_health.utils.nbr_vat_api.download_vat_excel?company=${encodeURIComponent(company)}&from_date=${from_date}&to_date=${to_date}&tax_id=${encodeURIComponent(tax_id)}`;
			window.open(url, '_blank');
		});

		// Expand All / Collapse All listeners (Delegated robustly)
		$wrapper.on('click', '.btn-expand-all-tree', function() {
			frm.report_state.collapsed_groups = [];
			$wrapper.find('.parent-node').removeClass('collapsed');
			$wrapper.find('.child-node').show();
		});

		$wrapper.on('click', '.btn-collapse-all-tree', function() {
			frm.report_state.collapsed_groups = ['sales', 'purch', 'net'];
			$wrapper.find('.parent-node').addClass('collapsed');
			$wrapper.find('.child-node').hide();
		});

		// Tree nodes expand/collapse click (Delegated robustly)
		$wrapper.on('click', '.parent-node', function() {
			let group = $(this).data('group');
			let idx = frm.report_state.collapsed_groups.indexOf(group);
			
			if (idx === -1) {
				frm.report_state.collapsed_groups.push(group);
				$(this).addClass('collapsed');
				$wrapper.find(`[data-parent-group="${group}"]`).hide();
			} else {
				frm.report_state.collapsed_groups.splice(idx, 1);
				$(this).removeClass('collapsed');
				$wrapper.find(`[data-parent-group="${group}"]`).show();
			}
		});

		// Back navigation links (Delegated robustly)
		$wrapper.on('click', '.btn-back-level1', function(e) {
			e.preventDefault();
			frm.report_state.level = 1;
			frm.report_state.row_id = null;
			frm.report_state.category = null;
			frm.trigger('render_report');
		});

		$wrapper.on('click', '.btn-back-level2', function(e) {
			e.preventDefault();
			frm.report_state.level = 2;
			frm.report_state.category = null;
			frm.trigger('render_report');
		});

		// Summary row clicks Level 1 (Delegated robustly)
		$wrapper.on('click', '.child-node.clickable-row', function() {
			let row_id = $(this).data('row-id');
			frappe.call({
				method: 'beveren_health.beveren_health.utils.nbr_vat_api.get_category_breakup',
				args: {
					row_id: row_id,
					company: frm.doc.company,
					from_date: frm.doc.from_date,
					to_date: frm.doc.to_date,
					tax_id: frm.doc.tax_id || ''
				},
				freeze: true,
				callback: function(r) {
					frm.report_state.level = 2;
					frm.report_state.row_id = row_id;
					frm.category_data = r.message;
					frm.trigger('render_report');
				}
			});
		});

		// Category row clicks Level 2 (Delegated robustly)
		$wrapper.on('click', '.clickable-row.category-row', function() {
			let category = $(this).data('category');
			frappe.call({
				method: 'beveren_health.beveren_health.utils.nbr_vat_api.get_invoice_list',
				args: {
					row_id: frm.report_state.row_id,
					category: category,
					company: frm.doc.company,
					from_date: frm.doc.from_date,
					to_date: frm.doc.to_date,
					tax_id: frm.doc.tax_id || ''
				},
				freeze: true,
				callback: function(r) {
					frm.report_state.level = 3;
					frm.report_state.category = category;
					frm.invoice_list = r.message;
					frm.trigger('render_report');
				}
			});
		});
	}
});
