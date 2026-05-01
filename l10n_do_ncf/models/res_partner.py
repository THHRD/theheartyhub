from odoo import models, fields, api, _


class Partner(models.Model):
    _inherit = "res.partner"

    sale_fiscal_type_id = fields.Many2one(
        comodel_name="account.fiscal.type",
        string="Sale Fiscal Type",
        domain=[("type", "=", "out_invoice")],
        compute='_compute_sale_fiscal_type_id',
        inverse='_inverse_sale_fiscal_type_id',
        index=True,
        store=True,
    )
    purchase_fiscal_type_id = fields.Many2one(
        comodel_name="account.fiscal.type",
        string="Purchase Fiscal Type",
        domain=[("type", "=", "in_invoice")],
    )
    expense_type = fields.Selection(
        selection=[
            ("01", "01 - Personnel Expenses"),
            ("02", "02 - Work, Supplies and Services Expenses"),
            ("03", "03 - Leases"),
            ("04", "04 - Fixed Assets Expenses"),
            ("05", "05 - Representation Expenses"),
            ("06", "06 - Other Admitted Deductions"),
            ("07", "07 - Financial Expenses"),
            ("08", "08 - Extraordinary Expenses"),
            ("09", "09 - Purchases and Expenses that are part of Cost of Sale"),
            ("10", "10 - Asset Acquisitions"),
            ("11", "11 - Insurance Expenses"),
        ],
        string="Expense Type",
    )
    is_fiscal_info_required = fields.Boolean(
        compute="_compute_is_fiscal_info_required"
    )
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='Country',
        ondelete='restrict',
        default=lambda self: self.env.ref('base.do')
    )

    @api.depends('sale_fiscal_type_id', 'country_id', 'parent_id')
    def _compute_is_fiscal_info_required(self):
        for partner in self:
            partner.is_fiscal_info_required = partner.sale_fiscal_type_id and \
            partner.sale_fiscal_type_id.requires_document and \
            partner.country_id == self.env.ref('base.do') and \
            not partner.parent_id

    def _get_fiscal_type_domain(self, prefix):
        return self.env['account.fiscal.type'].search([
            ('type', '=', 'out_invoice'),
            ('prefix', '=', prefix),
        ], limit=1)

    @api.depends('vat', 'country_id', 'name')
    def _compute_sale_fiscal_type_id(self):
        for partner in self.sudo():
            vat = partner.name if partner.name and \
                isinstance(partner.name, str) and \
                partner.name.isdigit() else partner.vat

            is_dominican_partner = partner.country_id == self.env.ref('base.do')

            new_fiscal_type = self._determine_fiscal_type(partner, vat, is_dominican_partner)

            partner.sale_fiscal_type_id = new_fiscal_type
            partner.sudo().set_fiscal_position_from_fiscal_type(new_fiscal_type)

    def _determine_fiscal_type(self, partner, vat, is_dominican_partner):
        not_digit_name = partner.name and isinstance(partner.name, str) and not partner.name.isdigit()

        if not is_dominican_partner:
            return self._get_fiscal_type_domain('B16')

        elif partner.parent_id:
            return partner.parent_id.sale_fiscal_type_id

        elif vat and \
            isinstance(vat, str) and \
            not partner.sale_fiscal_type_id and \
            not_digit_name:
            
            return self._determine_fiscal_type_by_vat(partner, vat)

        elif is_dominican_partner and not partner.sale_fiscal_type_id and not_digit_name:
            return self._get_fiscal_type_domain('B02')

        else:
            return partner.sale_fiscal_type_id

    def _determine_fiscal_type_by_vat(self, partner, vat):
        if vat.isdigit() and len(vat) == 9:
            if 'MINISTERIO' in (partner.name or '').upper():
                return self._get_fiscal_type_domain('B15')
            if any(keyword in (partner.name or '').upper() for keyword in ('IGLESIA', 'ZONA FRANCA')):
                return self._get_fiscal_type_domain('B14')
            return self._get_fiscal_type_domain('B01')
        return self._get_fiscal_type_domain('B02')

    def _inverse_sale_fiscal_type_id(self):
        for partner in self:
            partner.sale_fiscal_type_id = partner.sale_fiscal_type_id
            self.sudo().set_fiscal_position_from_fiscal_type(partner.sale_fiscal_type_id)

    @api.model
    def get_sale_fiscal_type_id_selection(self):
        return {
            "sale_fiscal_type_id": self.sale_fiscal_type_id.id,
            "sale_fiscal_type_list": [
                {"id": "final", "name": _("Final Consumer"), "ticket_label": _("Consumer"), "is_default": True},
                {"id": "fiscal", "name": _("Tax Credit")},
                {"id": "gov", "name": _("Governmental")},
                {"id": "special", "name": _("Special Regimes")},
                {"id": "unico", "name": _("Single Income")},
                {"id": "export", "name": _("Exports")}
            ],
            "sale_fiscal_type_vat": {
                "rnc": ["fiscal", "gov", "special"],
                "ced": ["final", "fiscal"],
                "other": ["final"],
                "no_vat": ["final", "unico", "export"]
            }
        }

    def set_fiscal_position_from_fiscal_type(self, fiscal_type):
        if fiscal_type:
            for company in self.env['res.company'].sudo().search([]):
                company_new_fiscal_type = fiscal_type.with_company(company).sudo()

                if company_new_fiscal_type.fiscal_position_id:
                    self.with_company(company).sudo().write({
                        'property_account_position_id': company_new_fiscal_type.fiscal_position_id.id
                    })
