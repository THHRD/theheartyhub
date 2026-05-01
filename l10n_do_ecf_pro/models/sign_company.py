from datetime import datetime
"""
pip install pyarmor

(Osfuscar programas python sin expiracion)
pyarmor gen account_move.py account_move_line.py company.py sign.py sign_company.py

(Osfuscar programas python con expiracion)
pyarmor gen --expired 2023-08-27 account_move.py account_move_line.py company.py sign.py sign_company.py
OJO: cuando expira da un error le libreria que no deja ingresar al sistema
Internal Server Error
"""
#ecf_rnc = ['130097372','131372945']
ecf_rnc = ['131372945','132321839','130097372','101564415','131778623','131429841','131194796']
ecf_expiracion = '2099-08-27'
ecf_expiracion = datetime.strptime(ecf_expiracion, "%Y-%m-%d")
