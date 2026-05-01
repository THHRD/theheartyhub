OBTENER LOS TOTALES Y RESUMEN IMPUESTOS,
    Se deben crear los siguientes grupos de Impuestos:
    ITBIS1 = 18% ITbis
    ITBIS2 = 16% de Itbis
    ITBIS3 = 0% de Itbis (Gravados pero el cliente no paga ITBIS)
    RITBIS = Retencion de Itbis
    EXENTO = Exento
    ISR    = Retencion de Impuestos Sobre la Renta
    XXX-ISCE = Impuesto adicional selectivo Especifico (donde xxx es codigo DGII ejemplo 006-ISCE) 
    XXX-ISCA = Impuesto adicional selectivo Advalorem
    XXX-ISCO = Impuesto selectivo al consumo, Otros

PARA LAS UNIDADES DE MEDIDAS CON CODIGO DGII
    En la descripcion de la unidad de medida se debe crear primero el codigo con un guion (-)
    y luego la descripcion, ej.: 43-Unidad

NOTA: ver codigos y validaciones al archivo en schema

***

# Se deben crear los siguientes Grupos de Impuestos (formato en modo tabla)

Este documento lista los códigos de impuestos a configurar en el sistema, detallando su definición según el requerimiento.

## Grupos de Impuestos y Retenciones (Códigos de Configuración)

| Código del Impuesto | Descripción / Definición |
| :--- | :--- |
| **ITBIS1** | 18% ITbis |
| **ITBIS2** | 16% de Itbis |
| **ITBIS3** | 0% de Itbis (Gravados pero el cliente no paga ITBIS) |
| **RITBIS** | Retencion de Itbis |
| **EXENTO** | Exento |
| **ISR** | Retencion de Impuestos Sobre la Renta |
| **XXX-ISCE** | Impuesto adicional selectivo Especifico (donde xxx es codigo DGII ejemplo 006-ISCE) |
| **XXX-ISCA** | Impuesto adicional selectivo Advalorem |
| **XXX-ISCO** | Impuesto selectivo al consumo, Otros |