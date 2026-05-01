from odoo import models, fields, api, _


class ResUom(models.Model):
    _inherit = "uom.uom"
    
    ecf_code  = fields.Char(string='Codigo ECF',default="42")
    ecf_name  = fields.Char(string='Descripcion ECF',default="42-Unidad")
