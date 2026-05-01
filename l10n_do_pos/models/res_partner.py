from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _load_pos_data_fields(self, config_id):
        fields_list = super()._load_pos_data_fields(config_id)
        if "sale_fiscal_type_id" not in fields_list:
            fields_list.append("sale_fiscal_type_id")
        return fields_list
