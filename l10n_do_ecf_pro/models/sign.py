# -*- coding: utf-8 -*-
import logging
_logger = logging.getLogger(__name__)

from io import BytesIO
import json
import base64
import hashlib

from datetime import datetime, timezone, timedelta

import requests
from lxml import etree

# signxml sigue siendo el motor de firma XML (XMLDSIG)
try:
    from .. import signxml
except ImportError:
    from ... import signxml

# === NUEVO: usar cryptography en lugar de OpenSSL/pyOpenSSL ===
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

parser = etree.XMLParser(remove_blank_text=True)


class XMLSignature:
    """
    Implementación compatible con tu versión anterior,
    pero usando 'cryptography' en lugar de pyOpenSSL.
    Mantiene los mismos métodos públicos:
      - _get_key()
      - _get_pem()
      - _get_rsa_pkey()
      - _get_semilla()
      - _get_token_semilla()
      - _generate_signature()
      - _sign_xml()
      - _validate_ecf()
      - _resultado_ecf()
      - _directorios_url()
      - _aprobacion_comercial()
      - _envio_comprador()
    """

    def __init__(self, cert, password, ambiente):
        # 'cert' llega como base64 del binario en Odoo (Binary), lo conservamos.
        self.cert = cert
        self.password = password or ""
        self.ambiente = ambiente

        # cache de clave y certificado (objetos cryptography)
        self._private_key = None
        self._certificate = None
        self._addl_certs = None

    # ---------------------------------------------------------------------
    #      CARGA PKCS#12 CON CRYPTOGRAPHY  (reemplaza pyOpenSSL)
    # ---------------------------------------------------------------------
    def _get_key(self):
        """
        Carga el .p12/.pfx contenido en self.cert (base64) y devuelve
        una tupla (private_key, certificate, additional_certs) de 'cryptography'.
        Mantiene el nombre del método para compatibilidad.
        """
        if self._private_key and self._certificate is not None:
            return self._private_key, self._certificate, self._addl_certs

        try:
            pkcs12_bytes = base64.b64decode(self.cert or b"")
        except Exception as e:
            raise ValueError(f"Certificado base64 inválido: {e}")

        try:
            private_key, certificate, additional_certs = load_key_and_certificates(
                data=pkcs12_bytes,
                password=self.password.encode() if self.password else None,
            )
        except Exception as e:
            raise ValueError(f"Error al cargar PKCS#12: {e}")

        if not private_key or not certificate:
            raise ValueError("El archivo PKCS#12 no contiene clave o certificado válido.")

        self._private_key = private_key
        self._certificate = certificate
        self._addl_certs = additional_certs or []
        return self._private_key, self._certificate, self._addl_certs

    def _get_pem(self, cert_obj):
        """
        Devuelve el certificado X.509 en formato PEM (bytes).
        Antes: esperaba un objeto PKCS12; ahora recibe el cert (cryptography.x509.Certificate).
        """
        try:
            return cert_obj.public_bytes(encoding=serialization.Encoding.PEM)
        except Exception as e:
            raise ValueError(f"No se pudo convertir certificado a PEM: {e}")

    def _get_rsa_pkey(self, private_key_obj):
        """
        Devuelve la clave privada en formato PEM PKCS8 (bytes), sin passphrase.
        Antes: dump de pyOpenSSL; ahora con cryptography.
        """
        try:
            return private_key_obj.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        except Exception as e:
            raise ValueError(f"No se pudo exportar la clave privada a PEM: {e}")

    # ---------------------------------------------------------------------
    #                            DGII: Semilla / Token
    # ---------------------------------------------------------------------
    def _get_semilla(self):
        url_semilla = f"https://ecf.dgii.gov.do/{self.ambiente}/autenticacion/api/Autenticacion/Semilla"
        headers_semilla = {"accept": "application/xml"}
        try:
            response = requests.get(url_semilla, headers=headers_semilla, timeout=10)
            if response.status_code == 200:
                return response.content
            _logger.error("DGII Semilla HTTP %s: %s", response.status_code, response.text)
            return False
        except requests.RequestException as err:
            _logger.error("Error solicitando semilla DGII: %s", err)
            return False

    def _get_token_semilla(self):
        """
        1) Obtiene semilla (XML)
        2) La firma con el certificado
        3) Envía a ValidarSemilla y devuelve el JSON con el token (o False)
        """
        url_val_semilla = f"https://ecf.dgii.gov.do/{self.ambiente}/autenticacion/api/Autenticacion/ValidarSemilla"

        if not self._check_internet_connection():
            _logger.error("No hay conexión a internet. No se puede obtener semilla DGII.")
            return False

        data_xml_document = self._get_semilla()
        if not data_xml_document:
            _logger.error("No se pudo obtener la semilla de DGII.")
            return False

        _xml = etree.XML(data_xml_document, parser=parser)
        xml_signature = self._generate_signature(_xml)

        output = BytesIO(xml_signature)
        output.name = "semilla.xml"
        files = {"xml": output}

        try:
            response = requests.post(url_val_semilla, files=files, timeout=20)
        except requests.RequestException as e:
            _logger.error("Error al validar semilla: %s", e)
            return False

        try:
            return response.json()
        except Exception as e:
            _logger.error("Respuesta no JSON de ValidarSemilla: %s", e)
            return False

    # ---------------------------------------------------------------------
    #                              Firma XML
    # ---------------------------------------------------------------------
    def _generate_signature(self, xml_document):
        """
        Firma el XML usando signxml y el par (clave privada + certificado) en PEM.
        Devuelve el XML firmado en bytes (UTF-8).
        """
        try:
            private_key_obj, cert_obj, _ = self._get_key()
            pkey_pem = self._get_rsa_pkey(private_key_obj)
            cert_pem = self._get_pem(cert_obj)

            signer = signxml.XMLSigner(
                c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
                signature_algorithm="rsa-sha256",
                digest_algorithm="sha256",
            )
            # Importante: mover el namespace ds como default si tu backend lo requiere
            signer.namespaces = {None: signer.namespaces["ds"]}

            signed = signer.sign(xml_document, key=pkey_pem, cert=cert_pem)
            return etree.tostring(signed, xml_declaration=False, encoding="UTF-8")
        except Exception as e:
            # Mantener comportamiento de tu versión (retornar Exception)
            return e

    def _sign_xml(self, xml):
        """
        Firma XML ECF o RFCE:
         - Inserta FechaHoraFirma en ECF
         - Firma
         - Extrae código de seguridad (primeros 6 de SignatureValue)
         - Devuelve (xml_firmado_bytes, CodigoSeguridad, FechaHora[datetime])
        """
        _xml = etree.XML(xml, parser=parser)

        zona_horaria = timezone(timedelta(hours=-4))  # GMT-4 RD
        FechaHora = datetime.now(tz=zona_horaria)

        if _xml.tag == "ECF":
            FechaHoraTxt = FechaHora.strftime("%d-%m-%Y %H:%M:%S")
            # Evita duplicar tag si ya existe
            existing = _xml.find("FechaHoraFirma")
            if existing is None:
                FechaHoraFirma = etree.SubElement(_xml, "FechaHoraFirma")
                FechaHoraFirma.text = FechaHoraTxt
            else:
                existing.text = FechaHoraTxt

        # Firmar
        signed_or_exc = self._generate_signature(_xml)
        if isinstance(signed_or_exc, Exception):
            raise signed_or_exc

        _xml_signed = etree.XML(signed_or_exc, parser=parser)

        # Obtener SignatureValue
        ns = "{http://www.w3.org/2000/09/xmldsig#}"
        cs = _xml_signed.find(f"{ns}Signature/{ns}SignatureValue")
        if cs is None or not cs.text:
            raise ValueError("No se pudo encontrar SignatureValue en el XML firmado.")
        CodigoSeguridad = cs.text[:6]

        xml_signature = etree.tostring(_xml_signed, xml_declaration=False, encoding="UTF-8")
        return xml_signature, CodigoSeguridad, FechaHora

    # ---------------------------------------------------------------------
    #                            Envíos a DGII
    # ---------------------------------------------------------------------
    def _validate_ecf(self, xml_signature, file_name, token):
        """
        Envía el XML firmado a DGII (ECF o RFCE) y devuelve (json, texto_crudo)
        """
        _xml = etree.XML(xml_signature, parser=parser)
        if _xml.tag == "ECF":
            url_val_ecf = f"https://ecf.dgii.gov.do/{self.ambiente}/recepcion/api/FacturasElectronicas"
        else:
            url_val_ecf = f"https://fc.dgii.gov.do/{self.ambiente}/RecepcionFC/api/Recepcion/ecf"

        output = BytesIO(xml_signature)
        output.name = file_name
        files = {"xml": output}
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}

        try:
            response = requests.post(url_val_ecf, files=files, headers=headers, timeout=30)
        except requests.RequestException as e:
            _logger.error("Error al enviar ECF a DGII: %s", e)
            return None, str(e)

        try:
            resp_json = response.json()
        except Exception:
            resp_json = None

        return resp_json, response.text

    def _resultado_ecf(self, trackid, token):
        url = f"https://eCF.dgii.gov.do/{self.ambiente}/ConsultaResultado/api/Consultas/Estado?TrackId={trackid}"
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}

        try:
            response = requests.get(url, headers=headers, timeout=20)
            resp = response.json()
        except requests.RequestException as e:
            _logger.error("Error consultando resultado ECF: %s", e)
            return False, False
        except Exception:
            return False, False

        if response.status_code == 200:
            return response.text, resp.get("codigo")
        return False, False

    def _directorios_url(self, token, rnc=None):
        if rnc:
            url = f"https://ecf.dgii.gov.do/{self.ambiente}/ConsultaDirectorio/api/Consultas/ObtenerDirectorioPorRnc?RNC={rnc}"
        else:
            url = f"https://ecf.dgii.gov.do/{self.ambiente}/Consultadirectorio/api/Consultas/Listado"

        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}

        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                return response.json()
            return False
        except requests.RequestException as e:
            _logger.error("Error consultando directorio DGII: %s", e)
            return False

    def _aprobacion_comercial(self, xml_signature, file_name, token, url):
        """
        Envía ACECF al proveedor (si url) o a la DGII.
        """
        if url:
            url_val = url.rstrip("/") + "/fe/aprobacioncomercial/api/ecf"
        else:
            url_val = f"https://ecf.dgii.gov.do/{self.ambiente}/AprobacionComercial/api/AprobacionComercial"

        output = BytesIO(xml_signature)
        output.name = file_name
        files = {"xml": output}
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}

        try:
            response = requests.post(url_val, files=files, headers=headers, timeout=30)
        except requests.RequestException as e:
            _logger.error("Error enviando ACECF: %s", e)
            return str(e)

        return response.text

    def _envio_comprador(self, xml_signature, file_name, token, url):
        """
        Envía el ECF al receptor (URL del receptor).
        """
        url_val = url.rstrip("/") + "/fe/recepcion/api/ecf"

        output = BytesIO(xml_signature)
        output.name = file_name
        files = {"xml": output}
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}

        try:
            response = requests.post(url_val, files=files, headers=headers, timeout=30)
        except requests.RequestException as e:
            _logger.error("Error enviando ECF al receptor: %s", e)
            return str(e)

        return response
    
    def _check_internet_connection(self):
        try:
            url = f"https://ecf.dgii.gov.do/{self.ambiente}/autenticacion/api/Autenticacion/Semilla"
            r = requests.get(url, timeout=5)
            return r.status_code in (200, 401, 403)
        except Exception:
            return False