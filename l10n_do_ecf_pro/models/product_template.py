# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, tools, _

class ProductProduct(models.Model):
    _inherit = "product.product"

    fecha_elaboracion = fields.Date(string="Fecha Elaboracion",related='product_tmpl_id.fecha_elaboracion')
    fecha_vencimiento = fields.Date(string="Fecha Vencimiento",related='product_tmpl_id.fecha_vencimiento')
    ecf_tipo_codigo = fields.Char(string="Tipo Codigo",related='product_tmpl_id.ecf_tipo_codigo')
    ecf_default_code = fields.Char(string="ECF Default Code",related='product_tmpl_id.ecf_default_code') 

class ProductTemplate(models.Model):
    _inherit = "product.template"

    fecha_elaboracion  = fields.Date(string="Fecha Elaboracion")
    fecha_vencimiento = fields.Date(string="Fecha Vencimiento")
    ecf_tipo_codigo = fields.Char(string="Tipo Codigo", default = "INTERNA")
    ecf_default_code = fields.Char(string="ECF Default Code") # Se repite el codigo en la Cerfificacion y Odoo no lo permite en Default code



    
