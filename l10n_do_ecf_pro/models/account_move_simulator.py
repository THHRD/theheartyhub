# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------
#  Simulador de flujo e-CF DGII (modo test)
#  Guarda XML firmado, semilla y respuesta en /opt/odoo17/ecf_test/
# ---------------------------------------------------------------------

import os
import time
import json
import base64
from datetime import datetime
from odoo import api, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

# 🔒 Protección: no cargar en producción
#if os.getenv("ODOO_ENV") == "production":
#    raise ImportError("El simulador e-CF está deshabilitado en modo producción.")


class AccountMoveSimulador(models.Model):
    _inherit = "account.move"

    def boton_simular_flujo_ecf(self):
        """
        Simulación completa del flujo e-CF:
        - Genera XML
        - Firma XML
        - Solicita token
        - Envía XML a DGII
        - Guarda semilla, firmado, respuesta JSON y log técnico
        """
        self.ensure_one()
        inv = self

        if not inv.is_ecf_invoice:
            raise UserError(_("Esta factura no es e-CF."))
        if not inv.company_id.cert or not inv.company_id.cert_password:
            raise UserError(_("Falta el certificado digital o la contraseña."))

        # ============================================================
        # 📁 Crear carpeta base y subcarpeta por factura
        # ============================================================
        base_dir = "/opt/odoo17/ecf_test"
        os.makedirs(base_dir, exist_ok=True)
        factura_dir = os.path.join(base_dir, inv.name.replace("/", "_"))
        os.makedirs(factura_dir, exist_ok=True)

        log_file = os.path.join(factura_dir, "log.txt")
        semilla_file = os.path.join(factura_dir, "semilla.xml")
        firmado_file = os.path.join(factura_dir, "firmado.xml")
        respuesta_file = os.path.join(factura_dir, "respuesta.json")

        def log_line(text):
            """Registrar línea en log y consola."""
            line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            _logger.info(line)
            return line

        log_line("=== INICIO SIMULACIÓN e-CF ===")
        log_line(f"Factura: {inv.name} | NCF: {inv.ref} | Ambiente: {inv.l10n_do_ecf_ambiente}")

        # ============================================================
        # 🧾 Importar clase de firma
        # ============================================================
        from ..models.sign import XMLSignature

        sign = XMLSignature(
            inv.company_id.cert,
            inv.company_id.cert_password,
            inv.company_id.l10n_do_ecf_ambiente or "CerteCF"
        )

        # ============================================================
        # 🌱 Obtener semilla (token)
        # ============================================================
        try:
            token_data = sign._get_token_semilla()
            token = token_data.get("token")
            semilla = token_data.get("semilla")
            log_line("✔ Semilla y token obtenidos correctamente.")
            if semilla:
                with open(semilla_file, "w", encoding="utf-8") as f:
                    f.write(semilla)
        except Exception as e:
            log_line(f"❌ Error al obtener semilla/token: {e}")
            raise UserError(f"Error obteniendo token DGII: {e}")

        # ============================================================
        # 🧩 Generar XML
        # ============================================================
        try:
            xml = self.xml_ecf(inv)
            log_line("✔ XML generado correctamente.")
        except Exception as e:
            log_line(f"❌ Error generando XML: {e}")
            raise UserError(f"Error generando XML: {e}")

        # ============================================================
        # ✍️ Firmar XML
        # ============================================================
        try:
            xml_firmado, codigo_seguridad, fecha_firma = sign._sign_xml(xml)
            inv.l10n_do_ecf_security_code = codigo_seguridad
            inv.l10n_do_ecf_sign_date = fecha_firma.replace(tzinfo=None)
            log_line(f"✔ XML firmado correctamente. Código de seguridad: {codigo_seguridad}")
            with open(firmado_file, "wb") as f:
                f.write(xml_firmado)
        except Exception as e:
            log_line(f"❌ Error firmando XML: {e}")
            raise UserError(f"Error firmando XML: {e}")

        # ============================================================
        # 📤 Enviar XML a DGII
        # ============================================================
        try:
            resp_json, resp_text = sign._validate_ecf(xml_firmado, inv.name + ".xml", token)
            if resp_json:
                log_line(f"✔ DGII respondió con código: {resp_json.get('codigo')}")
                with open(respuesta_file, "w", encoding="utf-8") as f:
                    json.dump(resp_json, f, indent=4, ensure_ascii=False)
            else:
                log_line(f"⚠ DGII no devolvió JSON. Texto: {resp_text[:500]}")
                with open(respuesta_file, "w", encoding="utf-8") as f:
                    f.write(resp_text)
        except Exception as e:
            log_line(f"❌ Error enviando XML a DGII: {e}")
            raise UserError(f"Error enviando XML DGII: {e}")

        # ============================================================
        # 🔍 Consultar resultado DGII
        # ============================================================
        try:
            trackid = None
            if isinstance(resp_json, dict):
                trackid = resp_json.get("trackid")
            if trackid:
                resp_text, codigo = sign._resultado_ecf(trackid, token)
                log_line(f"✔ Resultado DGII: código {codigo}")
                with open(os.path.join(factura_dir, "resultado.txt"), "w", encoding="utf-8") as f:
                    f.write(resp_text)
            else:
                log_line("⚠ No se obtuvo TrackID para consultar estado.")
        except Exception as e:
            log_line(f"⚠ Error consultando resultado DGII: {e}")

        log_line("=== FIN SIMULACIÓN e-CF ===")

        raise UserError(_(
            f"✅ Simulación completada.\n\n"
            f"Archivos guardados en:\n{factura_dir}\n\n"
            "Revise log.txt y firmado.xml para ver los detalles técnicos."
        ))
