# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountFiscalType(models.Model):
    _name = 'account.fiscal.type'
    _inherit = ["account.fiscal.type", "pos.load.mixin"]

    pos_available = fields.Boolean(string="¿Disponible en POS?")

    @api.model
    def _load_pos_data_fields(self, config_id):
        required_fields = [
            "id",
            "name",
            "requires_document",
            "fiscal_position_id",
            "prefix",
            "type",
            "pos_available",
        ]
        return required_fields

    @api.model
    def _load_pos_data_domain(self, data, config):
        domain = super()._load_pos_data_domain(data, config)
        return domain + [("pos_available", "=", True)]
