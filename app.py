# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Encuesta Comercio (Zona Comercial) → XLSForm para ArcGIS Survey123 (Páginas) + Cantón→Distrito + Glosario por página
#
# - Página 1: Introducción (logo + texto EXACTO de comercio)
# - Página 2: Consentimiento Informado (MISMO texto legal) + ¿Acepta participar? (Sí/No)
#            + Si responde "No" => finaliza (end)
# - Página 3: Datos demográficos (Cantón/Distrito + Edad por rangos + Género + Escolaridad + Tipo de local)
# - Página 4: Percepción ciudadana de seguridad en el comercio (7, 7.1, 8, 8.1, 9 matriz, 10 abierta)
# - Página 5: Riesgos/Delitos/Victimización (11 a 23.1 con condicionales)
# - Página 6: Mejora/Confianza/Programa/Contacto (24 a 34 con condicionales)
#
# - Glosario por página (voluntario): SOLO si hay coincidencias con el glosario
#   + Se muestra al final de la página si la persona elige "Sí" (NO obligatorio)
#   + El glosario queda DENTRO de la misma página (no crea navegación hacia adelante)
#
# - Exporta XLSForm (Excel) con hojas: survey / choices / settings
# - Mejora importante: notas (note) NO crean columnas en la tabla (bind::esri:fieldType="null")
# ==========================================================================================

import re
from io import BytesIO
from datetime import datetime

import streamlit as st
import pandas as pd

# ==========================================================================================
# Configuración
# ==========================================================================================
st.set_page_config(page_title="Encuesta Comercio — XLSForm (Survey123)", layout="wide")
st.title("🏪 Encuesta Comercio (Zona Comercial) → XLSForm para ArcGIS Survey123")

st.markdown("""
Genera un **XLSForm** listo para **ArcGIS Survey123** con páginas reales (Next/Back):
- **Página 1**: Introducción (logo + texto).
- **Página 2**: Consentimiento Informado (ordenado) + aceptación (Sí/No).
- **Página 3**: Datos demográficos (Cantón/Distrito en cascada + tipo de local).
- **Página 4**: Percepción de seguridad en el comercio (7 a 10).
- **Página 5**: Riesgos/Delitos/Victimización (11 a 23.1).
- **Página 6**: Confianza/Programa/Contacto (24 a 34).
- **Glosario por página**: solo se agrega cuando hay coincidencias con términos del glosario.
""")

# ==========================================================================================
# Helpers
# ==========================================================================================
def slugify_name(texto: str) -> str:
    """Convierte texto a un slug válido para XLSForm (name)."""
    if not texto:
        return "campo"
    t = texto.lower()
    t = re.sub(r"[áàäâ]", "a", t)
    t = re.sub(r"[éèëê]", "e", t)
    t = re.sub(r"[íìïî]", "i", t)
    t = re.sub(r"[óòöô]", "o", t)
    t = re.sub(r"[úùüû]", "u", t)
    t = re.sub(r"ñ", "n", t)
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t or "campo"

def asegurar_nombre_unico(base: str, usados: set) -> str:
    if base not in usados:
        return base
    i = 2
    while f"{base}_{i}" in usados:
        i += 1
    return f"{base}_{i}"

def descargar_xlsform(df_survey, df_choices, df_settings, nombre_archivo: str):
    """Genera y descarga el XLSForm (Excel)."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_survey.to_excel(writer, sheet_name="survey", index=False)
        df_choices.to_excel(writer, sheet_name="choices", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)

        wb = writer.book
        fmt_hdr = wb.add_format({"bold": True, "align": "left"})
        for sheet, df in (("survey", df_survey), ("choices", df_choices), ("settings", df_settings)):
            ws = writer.sheets[sheet]
            ws.freeze_panes(1, 0)
            ws.set_row(0, None, fmt_hdr)
            for col_idx, col_name in enumerate(df.columns):
                ws.set_column(col_idx, col_idx, max(14, min(90, len(str(col_name)) + 10)))

    buffer.seek(0)
    st.download_button(
        label=f"📥 Descargar XLSForm ({nombre_archivo})",
        data=buffer,
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

def add_choice_list(choices_rows, list_name: str, labels: list[str]):
    """Agrega una lista de choices (list_name/name/label)."""
    usados = set((r.get("list_name"), r.get("name")) for r in choices_rows)
    for lab in labels:
        row = {"list_name": list_name, "name": slugify_name(lab), "label": lab}
        key = (row["list_name"], row["name"])
        if key not in usados:
            choices_rows.append(row)
            usados.add(key)

# ==========================================================================================
# Logo + Delegación / Zona
# ==========================================================================================
DEFAULT_LOGO_PATH = "001.png"

col_logo, col_txt = st.columns([1, 3], vertical_alignment="center")

with col_logo:
    up_logo = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
    if up_logo:
        st.image(up_logo, caption="Logo cargado", use_container_width=True)
        st.session_state["_logo_bytes"] = up_logo.getvalue()
        st.session_state["_logo_name"] = up_logo.name
    else:
        try:
            st.image(DEFAULT_LOGO_PATH, caption="Logo (001.png)", use_container_width=True)
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"] = "001.png"
        except Exception:
            st.warning("Sube un logo para incluirlo en el XLSForm.")
            st.session_state["_logo_bytes"] = None
            st.session_state["_logo_name"] = "logo.png"

with col_txt:
    delegacion = st.text_input("Nombre del lugar / Delegación (Zona comercial)", value="San Carlos Oeste")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image`",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo dentro de la carpeta `media/` del proyecto Survey123 (Connect)."
    )

form_title = f"Encuesta comercio – {delegacion.strip()}" if delegacion.strip() else "Encuesta comercio"
st.markdown(f"### {form_title}")

# ==========================================================================================
# Página 1: Introducción (EXACTO de comercio)
# ==========================================================================================
INTRO_COMERCIO_EXACTA = (
    "Con el fin de hacer más segura la zona comercial de este distrito, deseamos concentrarnos en \n"
    "los problemas de seguridad más importantes que afectan a los negocios. Queremos trabajar \n"
    "en conjunto con el gobierno local, otras instituciones y las personas comerciantes para reducir \n"
    "los delitos y riesgos que afectan la actividad comercial. \n"
    "Es importante recordarle que la información que usted nos proporcione es confidencial y se \n"
    "utilizará únicamente para mejorar la seguridad en esta zona comercial."
)

# ==========================================================================================
# Página 2: Consentimiento (MISMO de la app anterior)
# ==========================================================================================
CONSENT_TITLE = "Consentimiento Informado para la Participación en la Encuesta"

CONSENT_PARRAFOS = [
    "Usted está siendo invitado(a) a participar de forma libre y voluntaria en una encuesta sobre seguridad, convivencia y percepción ciudadana, dirigida a personas mayores de 18 años.",
    "El objetivo de esta encuesta es recopilar información de carácter preventivo y estadístico, con el fin de apoyar la planificación de acciones de prevención, mejora de la convivencia y fortalecimiento de la seguridad en comunidades y zonas comerciales.",
    "La participación es totalmente voluntaria. Usted puede negarse a responder cualquier pregunta, así como retirarse de la encuesta en cualquier momento, sin que ello genere consecuencia alguna.",
    "De conformidad con lo dispuesto en el artículo 5 de la Ley N.º 8968, Ley de Protección de la Persona frente al Tratamiento de sus Datos Personales, se le informa que:"
]

CONSENT_BULLETS = [
    "Finalidad del tratamiento: La información recopilada será utilizada exclusivamente para fines estadísticos, analíticos y preventivos, y no para investigaciones penales, procesos judiciales, sanciones administrativas ni procedimientos disciplinarios.",
    "Datos personales: Algunos apartados permiten, de forma voluntaria, el suministro de datos personales o información de contacto.",
    "Tratamiento de los datos: Los datos serán almacenados, analizados y resguardados bajo criterios de confidencialidad y seguridad, conforme a la normativa vigente.",
    "Destinatarios y acceso: La información será conocida únicamente por el personal autorizado de la Fuerza Pública / Ministerio de Seguridad Pública, para los fines indicados. No será cedida a terceros ajenos a estos fines.",
    "Responsable de la base de datos: El Ministerio de Seguridad Pública, a través de la Dirección de Programas Policiales Preventivos, Oficina Estrategia Integral de Prevención para la Seguridad Pública (EIPSEP / Estrategia Sembremos Seguridad) será el responsable del tratamiento y custodia de la información recolectada.",
    "Derechos de la persona participante: Usted conserva el derecho a la autodeterminación informativa y a decidir libremente sobre el suministro de sus datos."
]

CONSENT_CIERRE = [
    "Las respuestas brindadas no constituyen denuncias formales, ni sustituyen los mecanismos legales correspondientes.",
    "Al continuar con la encuesta, usted manifiesta haber leído y comprendido la información anterior y otorga su consentimiento informado para participar."
]

# ==========================================================================================
# Glosario (BASE) — se usará por página solo si hay coincidencias
# (Se puede ampliar cuando compartas el Word del glosario)
# ==========================================================================================
GLOSARIO_DEFINICIONES = {
    "Extorsión": (
        "Extorsión: El que, para procurar un lucro injusto, obligare a otro, mediante intimidación o amenaza, "
        "a realizar u omitir un acto o negocio en perjuicio de su patrimonio o del de un tercero."
    ),
    "Daños a la propiedad": (
        "Daños a la propiedad: El que destruyere, inutilizare, hiciere desaparecer o deteriorare bienes, "
        "sean de naturaleza pública o privada, en perjuicio de persona física o jurídica."
    ),
    "Receptación": (
        "Receptación: Adquirir, recibir, ocultar o comercializar bienes de origen ilícito, con conocimiento "
        "o sospecha razonable de su procedencia."
    ),
    "Contrabando": (
        "Contrabando: Introducción, extracción o comercio de mercancías eludiendo controles aduaneros o "
        "tributarios, conforme al ordenamiento aplicable."
    ),
    "Búnker": (
        "Búnker: Punto fijo asociado a consumo o venta de drogas, usualmente en una vivienda o edificación; "
        "en la encuesta se utiliza como descriptor situacional."
    ),
    "Tacha": (
        "Tacha: Modalidad de robo mediante forzamiento de accesos (puertas, ventanas, cerraduras) para ingresar "
        "a vivienda, comercio o edificación."
    ),
    "Ganzúa": (
        "Ganzúa: Herramienta utilizada para manipular o abrir cerraduras sin la llave correspondiente."
    ),
    "Arrebato": (
        "Arrebato: Sustracción súbita de un bien que porta la víctima (por ejemplo, bolso o celular), mediante "
        "fuerza sorpresiva."
    ),
}

# ==========================================================================================
# Catálogo Cantón → Distrito (por lotes)
# - Permite múltiples distritos por cantón
# - Usa placeholders y choice_filter
# ==========================================================================================
if "choices_ext_rows" not in st.session_state:
    st.session_state.choices_ext_rows = []
if "choices_extra_cols" not in st.session_state:
    st.session_state.choices_extra_cols = set()

def _append_choice_unique(row: dict):
    key = (row.get("list_name"), row.get("name"))
    exists = any((r.get("list_name"), r.get("name")) == key for r in st.session_state.choices_ext_rows)
    if not exists:
        st.session_state.choices_ext_rows.append(row)

st.markdown("### 📚 Catálogo Cantón → Distrito (por lotes)")
with st.expander("Agrega un lote (un Cantón y uno o varios Distritos)", expanded=True):
    col_c1, col_c2 = st.columns([2, 3])
    canton_txt = col_c1.text_input("Cantón (una vez)", value="")
    distritos_txt = col_c2.text_area("Distritos del cantón (uno por línea)", value="", height=120)

    col_b1, col_b2, col_b3 = st.columns([1, 1, 2])
    add_lote = col_b1.button("Agregar lote", type="primary", use_container_width=True)
    clear_all = col_b2.button("Limpiar catálogo", use_container_width=True)

    if clear_all:
        st.session_state.choices_ext_rows = []
        st.success("Catálogo limpiado.")

    if add_lote:
        c = canton_txt.strip()
        distritos = [d.strip() for d in distritos_txt.splitlines() if d.strip()]
        if not c or not distritos:
            st.error("Debes indicar Cantón y al menos un Distrito (uno por línea).")
        else:
            slug_c = slugify_name(c)

            # columnas extra usadas por filtros/placeholder
            st.session_state.choices_extra_cols.update({"canton_key", "any"})

            # Placeholders (una sola vez por lista)
            _append_choice_unique({"list_name": "list_canton", "name": "__pick_canton__", "label": "— escoja un cantón —"})
            _append_choice_unique({"list_name": "list_distrito", "name": "__pick_distrito__", "label": "— escoja un cantón —", "any": "1"})

            # Cantón
            _append_choice_unique({"list_name": "list_canton", "name": slug_c, "label": c})

            # Distritos (múltiples por líneas)
            usados_d = set()
            for d in distritos:
                slug_d_base = slugify_name(d)
                slug_d = asegurar_nombre_unico(slug_d_base, usados_d)
                usados_d.add(slug_d)
                _append_choice_unique({"list_name": "list_distrito", "name": slug_d, "label": d, "canton_key": slug_c})

            st.success(f"Lote agregado: {c} → {len(distritos)} distrito(s).")

if st.session_state.choices_ext_rows:
    st.dataframe(
        pd.DataFrame(st.session_state.choices_ext_rows),
        use_container_width=True,
        hide_index=True,
        height=240
    )

# ==========================================================================================
# (PARTE 2 continúa): construir_xlsform() + choices base + páginas 1..6 + glosario por página + export
# ==========================================================================================
# ==========================================================================================
# ============================== PARTE 2/4 =================================
# ============ construir_xlsform() + choices base + Páginas 1 a 3 ===========
# ==========================================================================================

def construir_xlsform(form_title: str, logo_media_name: str, idioma: str, version: str):
    survey_rows = []
    choices_rows = []

    # =========================
    # Choices base
    # =========================
    list_yesno = "yesno"
    add_choice_list(choices_rows, list_yesno, ["Sí", "No"])
    v_si = slugify_name("Sí")
    v_no = slugify_name("No")

    # Género
    list_genero = "genero"
    add_choice_list(choices_rows, list_genero, ["Femenino", "Masculino", "Persona No Binaria", "Prefiero no decir"])

    # Escolaridad
    list_escolaridad = "escolaridad"
    add_choice_list(choices_rows, list_escolaridad, [
        "Ninguna",
        "Primaria incompleta",
        "Primaria completa",
        "Secundaria incompleta",
        "Secundaria completa",
        "Técnico",
        "Universitaria incompleta",
        "Universitaria completa",
    ])

    # Edad por rangos (según imagen comercio)
    list_edad_rangos = "edad_rangos"
    add_choice_list(choices_rows, list_edad_rangos, [
        "18 a 29 años",
        "30 a 44 años",
        "45 a 59 años",
        "60 años o más",
    ])

    # Tipo de local comercial (según imagen)
    list_tipo_local = "tipo_local"
    add_choice_list(choices_rows, list_tipo_local, [
        "Supermercado",
        "Pulpería / Licorera",
        "Restaurante / Soda",
        "Bar",
        "Tienda de artículos",
        "Gasolinera",
        "Servicios estéticos",
        "Puesto de lotería",
        "Ferretería",
        "Otro",
    ])

    # =========================
    # Página 4: Percepción (7..10) — listas base
    # =========================
    list_seguridad_5 = "seguridad_5"
    add_choice_list(choices_rows, list_seguridad_5, ["Muy inseguro", "Inseguro", "Ni seguro ni inseguro", "Seguro", "Muy seguro"])

    list_escala_1_5 = "escala_1_5"
    add_choice_list(choices_rows, list_escala_1_5, [
        "1 (Mucho Menos Seguro)",
        "2 (Menos Seguro)",
        "3 (Se mantiene igual)",
        "4 (Más Seguro)",
        "5 (Mucho Más Seguro)",
    ])

    # Matriz 1-5 + No aplica
    list_matriz_1_5_na = "matriz_1_5_na"
    add_choice_list(choices_rows, list_matriz_1_5_na, [
        "Muy inseguro (1)",
        "Inseguro (2)",
        "Ni seguro ni inseguro (3)",
        "Seguro (4)",
        "Muy seguro (5)",
        "No aplica",
    ])

    # 7.1 (selección múltiple: descriptores del comercio)
    list_causas_inseguridad_comercio = "causas_inseguridad_comercio"
    causas_71 = [
        "Venta de drogas",
        "Consumo de drogas",
        "Consumo de alcohol en vía pública",
        "Riñas o peleas",
        "Asaltos",
        "Robos o tachas",
        "Extorsiones o amenazas",
        "Daños a la propiedad",
        "Vandalismo",
        "Ventas informales desordenadas",
        "Personas en situación de calle",
        "Presencia de comportamientos o actividades inusuales en el entorno",
        "Intentos de cobro ilegal o exigencias indebidas a comercios",
        "Otro",
    ]
    add_choice_list(choices_rows, list_causas_inseguridad_comercio, causas_71)

    # =========================
    # Página 5: Riesgos/Delitos/Victimización (11..23.1) — listas
    # =========================
    # 11 Horarios inseguridad (multi)
    list_horarios_inseg = "horarios_inseguridad"
    add_choice_list(choices_rows, list_horarios_inseg, ["Mañana", "Tarde", "Noche", "Madrugada", "Todo el día"])

    # 12 Problemáticas situacionales (multi)
    list_problematicas_comercio = "problematicas_comercio"
    add_choice_list(choices_rows, list_problematicas_comercio, [
        "Personas en situación de calle",
        "Actividades sexuales comerciales en el entorno",
        "Consumo de alcohol en vía pública",
        "Acumulación de basura / aguas negras / alcantarillado deficiente",
        "Falta o deficiencia de alumbrado público",
        "Lotes baldíos y edificaciones abandonadas",
        "Ventas informales",
        "Intentos de cobro ilegal o exigencias indebidas en la zona comercial",
        "Otro",
    ])

    # 13 Consumo de drogas — dónde observado (multi)
    list_donde_drogas = "donde_drogas"
    add_choice_list(choices_rows, list_donde_drogas, [
        "Área pública (calle, aceras, alrededores del local)",
        "Área semipública (parques, lotes abandonados)",
        "No se observa consumo",
        "Otro",
    ])

    # 14 Infraestructura vial (multi)
    list_infra_vial = "infra_vial"
    add_choice_list(choices_rows, list_infra_vial, [
        "Calles en mal estado",
        "Falta de señalización",
        "Falta o deterioro de aceras",
        "Otro",
    ])

    # 15 Transporte (multi)
    list_transporte_afect = "transporte_afect"
    add_choice_list(choices_rows, list_transporte_afect, [
        "Transporte informal (piratas)",
        "Plataformas digitales mal estacionadas u obstruyendo vías",
        "Paradas de bus inseguras",
        "Otro",
    ])

    # 16 Presencia policial (multi)
    list_presencia_policial = "presencia_policial_comercio"
    add_choice_list(choices_rows, list_presencia_policial, [
        "Falta de presencia policial",
        "Patrullaje insuficiente",
        "Presencia policial solo en ciertos horarios",
        "No observa presencia policial",
        "Otro",
    ])

    # 17 Delitos (multi)
    list_delitos_comercio = "delitos_comercio"
    add_choice_list(choices_rows, list_delitos_comercio, [
        "Disturbios en vía pública (riñas o agresiones)",
        "Daños a la propiedad",
        "Extorsión (cobro ilegal a comercios)",
        "Hurto (por descuido)",
        "Compra o venta de bienes de dudosa procedencia (receptación)",
        "Contrabando (licor, cigarrillos, medicinas, ropa, calzado, etc.)",
        "Maltrato animal",
        "Otro",
    ])

    # 18 Manifestación consumo/venta drogas (multi)
    list_manifest_drogas = "manifest_drogas"
    add_choice_list(choices_rows, list_manifest_drogas, [
        "Búnker / espacio cerrado",
        "Vía pública",
        "Modalidad exprés",
        "Otro",
    ])

    # 19 Tipos de asaltos (multi)
    list_asaltos_tipo = "asaltos_tipo"
    add_choice_list(choices_rows, list_asaltos_tipo, [
        "Asalto a personas",
        "Asalto a comercios",
        "Asalto en transporte público",
        "Otro",
    ])

    # 20 Estafas (multi)
    list_estafas = "estafas_comercio"
    add_choice_list(choices_rows, list_estafas, [
        "Billetes falsos",
        "Documentos falsos",
        "Estafas con oro",
        "Estafas con lotería",
        "Estafas informáticas",
        "Estafa telefónica",
        "Estafa con tarjetas",
        "Otro",
    ])

    # 21 Robos con fuerza (multi)
    list_robos_fuerza = "robos_fuerza"
    add_choice_list(choices_rows, list_robos_fuerza, [
        "Tacha a comercio",
        "Tacha a edificaciones comerciales",
        "Tacha de vehículos",
        "Robo de vehículos",
        "Robo de cable",
        "Robo de combustible",
        "Otro",
    ])

    # 22 Victimización (única)
    list_victim_22 = "victim_22"
    add_choice_list(choices_rows, list_victim_22, [
        "No",
        "Sí, y denuncié",
        "Sí, pero no denuncié",
    ])

    # 22.1 Delitos por categorías (multi) — lo mantenemos como una sola lista (tal como venimos trabajando)
    list_delitos_afectacion = "delitos_afectacion"
    add_choice_list(choices_rows, list_delitos_afectacion, [
        # A. Robo y Asalto
        "Asalto a mano armada (amenaza con arma o uso de violencia) en la calle o espacio público",
        "Asalto en el transporte público (bus, taxi, metro, etc.)",
        "Asalto o robo de su vehículo (coche, motocicleta, etc.)",
        "Robo de accesorios o partes de su vehículo (espejos, llantas, radio)",
        "Robo o intento de robo con fuerza a su vivienda (ej. forzar una puerta o ventana)",
        "Robo o intento de robo con fuerza a su comercio o negocio",
        # B. Hurto y Daños
        "Hurto de su cartera, bolso o celular (sin que se diera cuenta, por descuido)",
        "Daños a su propiedad (ej. grafitis, rotura de cristales, destrucción de cercas)",
        "Receptación (alguien compró o recibió un artículo y luego supo que era robado)",
        "Pérdida de artículos (celular, bicicleta, etc.) por descuido",
        # C. Fraude y Engaño
        "Estafa telefónica (llamadas para pedir dinero o datos personales)",
        "Estafa o fraude informático (internet, redes sociales o correo electrónico)",
        "Fraude con tarjetas bancarias (clonación o uso no autorizado)",
        "Ser víctima de billetes o documentos falsos",
        # D. Otros
        "Extorsión (intimidación o amenaza para obtener dinero u otro beneficio)",
        "Maltrato animal (fue testigo o su mascota fue la víctima)",
        "Acoso o intimidación sexual en un espacio público",
        "Algún tipo de delito sexual (abuso, violación)",
        "Lesiones personales (haber sido herido en una riña o agresión)",
        "Violencia intrafamiliar (violencia doméstica)",
        "Otro",
    ])

    # 22.2 Motivo no denunciar (multi)
    list_no_denuncia = "motivo_no_denuncia"
    add_choice_list(choices_rows, list_no_denuncia, [
        "Distancia (falta de oficinas para recepción de denuncias)",
        "Miedo a represalias",
        "Falta de respuesta oportuna",
        "He realizado denuncias y no ha pasado nada",
        "Complejidad al colocar la denuncia",
        "Desconocimiento de dónde colocar la denuncia",
        "El Policía me dijo que era mejor no denunciar",
        "Falta de tiempo para colocar la denuncia",
    ])

    # 22.3 Horario (única)
    list_horario_hecho = "horario_hecho"
    add_choice_list(choices_rows, list_horario_hecho, [
        "00:00 - 02:59 a. m.",
        "03:00 - 05:59 a. m.",
        "06:00 - 08:59 a. m.",
        "09:00 - 11:59 a. m.",
        "12:00 - 14:59 p. m.",
        "15:00 - 17:59 p. m.",
        "18:00 - 20:59 p. m.",
        "21:00 - 23:59 p. m.",
        "DESCONOCIDO",
    ])

    # 23 Forma/modo (multi)
    list_modo_ocurrio = "modo_ocurrio"
    add_choice_list(choices_rows, list_modo_ocurrio, [
        "Arma blanca (cuchillo, machete, tijeras)",
        "Arma de fuego",
        "Amenazas",
        "Arrebato",
        "Boquete",
        "Ganzúa (pata de chancho)",
        "Engaño",
        "No sé",
        "Otro",
    ])

    # 23.1 Incidentes de seguridad asociados a la operación (multi)
    list_incidentes_operacion = "incidentes_operacion"
    add_choice_list(choices_rows, list_incidentes_operacion, [
        "Riñas o disturbios dentro del local",
        "Riñas o disturbios en las inmediaciones del comercio",
        "Agresiones físicas al personal del comercio",
        "Amenazas verbales al personal",
        "Ingreso de personas en estado de ebriedad o bajo efectos de drogas que generaron conflictos",
        "Daños ocasionados por clientes o terceros",
        "Ninguno de los anteriores",
    ])

    # =========================
    # Página 6: Confianza / Programa / Contacto (24..34) — listas
    # =========================
    # 24 FP (multi con "No indica")
    list_act_fp = "act_fp"
    add_choice_list(choices_rows, list_act_fp, [
        "Mayor presencia policial y patrullaje",
        "Acciones disuasivas en puntos conflictivos",
        "Acciones contra consumo y venta de drogas",
        "Mejorar el servicio policial de la zona comercial",
        "Acercamiento comercial",
        "Actividades de prevención y educación",
        "Coordinación interinstitucional",
        "Integridad y credibilidad policial",
        "Otro",
        "No indica",
    ])

    # 25 Municipalidad (multi con "No indica")
    list_act_muni = "act_muni"
    add_choice_list(choices_rows, list_act_muni, [
        "Mantenimiento e iluminación del espacio público en áreas comerciales",
        "Limpieza, recolección de desechos y ordenamiento urbano",
        "Instalación de cámaras municipales y vigilancia en puntos comerciales",
        "Control de ventas informales y ocupación indebida del espacio público",
        "Regulación del transporte informal y mejora de paradas de bus",
        "Mejoramiento de aceras, calles y espacios públicos del casco comercial",
        "Coordinación interinstitucional con Fuerza Pública y otras entidades",
        "Acercamiento y comunicación directa con las personas comerciantes",
        "Otro",
        "No indica",
    ])

    # 26 Servicio policial últimos 24 meses (única)
    list_servicio_24m = "servicio_24m"
    add_choice_list(choices_rows, list_servicio_24m, ["Mejor servicio", "Igual", "Peor servicio"])

    # 27 Conoce policías (sí/no) reutiliza yesno
    # 28 Conoce programa seguridad comercial (sí/no) reutiliza yesno
    # 29 Está inscrito (sí/no) reutiliza yesno
    # 30 Desea contacto (sí/no) reutiliza yesno

    # 32 Info de persona/grupo delito (sí/no) reutiliza yesno

    # =========================
    # Utilidad: notes sin campo (para que NO salgan columnas vacías)
    # =========================
    def add_note(name: str, label: str, relevant: str | None = None, media_image: str | None = None):
        row = {"type": "note", "name": name, "label": label, "bind::esri:fieldType": "null"}
        if relevant:
            row["relevant"] = relevant
        if media_image:
            row["media::image"] = media_image
        survey_rows.append(row)

    # ======================================================================================
    # PÁGINA 1 — INTRODUCCIÓN (COMERCIO)
    # ======================================================================================
    survey_rows.append({"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"})
    add_note("p1_logo", form_title, media_image=logo_media_name)
    add_note("p1_texto", INTRO_COMERCIO_EXACTA)
    survey_rows.append({"type": "end_group", "name": "p1_end"})

    # ======================================================================================
    # PÁGINA 2 — CONSENTIMIENTO
    # ======================================================================================
    survey_rows.append({"type": "begin_group", "name": "p2_consent", "label": "Consentimiento Informado", "appearance": "field-list"})
    add_note("p2_titulo", CONSENT_TITLE)

    for i, p in enumerate(CONSENT_PARRAFOS, start=1):
        add_note(f"p2_p_{i}", p)

    for j, b in enumerate(CONSENT_BULLETS, start=1):
        add_note(f"p2_b_{j}", f"• {b}")

    for k, c in enumerate(CONSENT_CIERRE, start=1):
        add_note(f"p2_c_{k}", c)

    survey_rows.append({
        "type": f"select_one {list_yesno}",
        "name": "acepta_participar",
        "label": "¿Acepta participar en esta encuesta?",
        "required": "yes",
        "appearance": "minimal"
    })
    survey_rows.append({"type": "end_group", "name": "p2_end"})

    # Finalizar si NO acepta
    survey_rows.append({
        "type": "end",
        "name": "fin_por_no",
        "label": "Gracias. Usted indicó que no acepta participar en esta encuesta.",
        "relevant": f"${{acepta_participar}}='{v_no}'"
    })

    rel_si = f"${{acepta_participar}}='{v_si}'"

    # ======================================================================================
    # PÁGINA 3 — DATOS DEMOGRÁFICOS (COMERCIO)
    # ======================================================================================
    survey_rows.append({
        "type": "begin_group",
        "name": "p3_datos_demograficos",
        "label": "Datos demográficos",
        "appearance": "field-list",
        "relevant": rel_si
    })

    # 1. Cantón
    survey_rows.append({
        "type": "select_one list_canton",
        "name": "canton",
        "label": "1. Cantón:",
        "required": "yes",
        "constraint": ". != '__pick_canton__'",
        "constraint_message": "Seleccione un cantón válido.",
        "appearance": "minimal",
        "relevant": rel_si
    })
    add_note("p3_nota_canton", "Nota: La respuesta es de opción desplegable.", relevant=rel_si)

    # 2. Distrito
    survey_rows.append({
        "type": "select_one list_distrito",
        "name": "distrito",
        "label": "2. Distrito:",
        "required": "yes",
        "choice_filter": "canton_key=${canton} or any='1'",
        "constraint": ". != '__pick_distrito__'",
        "constraint_message": "Seleccione un distrito válido.",
        "appearance": "minimal",
        "relevant": rel_si
    })
    add_note("p3_nota_distrito", "Nota: La respuesta es de opción desplegable.", relevant=rel_si)

    # 3. Edad por rangos
    survey_rows.append({
        "type": f"select_one {list_edad_rangos}",
        "name": "edad_rango",
        "label": "3. Edad (en años cumplidos): marque con una X la categoría que incluya su rango de edad.",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    add_note(
        "p3_nota_edad",
        "Nota: Esta pregunta se responde mediante rangos de edad. Solo pueden participar personas adultas (18 años o más), "
        "por lo que las personas menores de edad quedan excluidas conforme al consentimiento informado.",
        relevant=rel_si
    )

    # 4. Género
    survey_rows.append({
        "type": f"select_one {list_genero}",
        "name": "genero",
        "label": "4. ¿Con cuál de estas opciones se identifica?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    add_note("p3_nota_genero", "Nota: La respuesta es de selección única.", relevant=rel_si)

    # 5. Escolaridad
    survey_rows.append({
        "type": f"select_one {list_escolaridad}",
        "name": "escolaridad",
        "label": "5. Escolaridad:",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    add_note("p3_nota_escolaridad", "Nota: La respuesta es de selección única.", relevant=rel_si)

    # 6. Tipo de local comercial
    survey_rows.append({
        "type": f"select_one {list_tipo_local}",
        "name": "tipo_local",
        "label": "6. Tipo de local comercial",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })
    add_note("p3_nota_tipo_local", "Nota: la respuesta es de selección única.", relevant=rel_si)

    # 6.1 Otro (detalle)
    survey_rows.append({
        "type": "text",
        "name": "tipo_local_otro",
        "label": "Otro (especifique):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and (${{tipo_local}}='{slugify_name('Otro')}')"
    })

    survey_rows.append({"type": "end_group", "name": "p3_end"})

    # ======================================================================================
    # Integrar catálogo Cantón→Distrito en choices
    # ======================================================================================
    for r in st.session_state.choices_ext_rows:
        choices_rows.append(dict(r))

    # ======================================================================================
    # (PARTE 3 continúa): Páginas 4, 5 y 6 completas + glosario por página + DataFrames + export
    # ======================================================================================
    return survey_rows, choices_rows, rel_si, v_si, v_no


# ==========================================================================================
# Nota: en Parte 3 se completa el XLSForm y se construyen df_survey/df_choices/df_settings.
# ==========================================================================================
# ==========================================================================================
# ============================== PARTE 3/4 =================================
# ======== Páginas 4, 5 y 6 + Glosario por página + DataFrames XLSForm ======
# ==========================================================================================

# --- Completar / ampliar glosario base (si aplica) ---
# (Se mantiene el mismo mecanismo: glosario voluntario por página, dentro de la misma página)
if "Boquete" not in GLOSARIO_DEFINICIONES:
    GLOSARIO_DEFINICIONES["Boquete"] = (
        "Boquete: Modalidad de ingreso forzado mediante apertura de un hueco u orificio en paredes, techos "
        "u otras estructuras para acceder a un inmueble."
    )

def construir_xlsform_completo(form_title: str, logo_media_name: str, idioma: str, version: str):
    # Reusamos la Parte 2 (choices + páginas 1..3) y seguimos agregando todo lo faltante
    survey_rows, choices_rows, rel_si, v_si, v_no = construir_xlsform(
        form_title=form_title,
        logo_media_name=logo_media_name,
        idioma=idioma,
        version=version
    )

    # ======================================================================================
    # Utilidad: notes sin campo (para que NO salgan columnas vacías)
    # ======================================================================================
    def add_note(name: str, label: str, relevant: str | None = None):
        row = {"type": "note", "name": name, "label": label, "bind::esri:fieldType": "null"}
        if relevant:
            row["relevant"] = relevant
        survey_rows.append(row)

    # ======================================================================================
    # PÁGINA 4 — II. PERCEPCIÓN CIUDADANA DE SEGURIDAD EN EL COMERCIO (7 a 10)
    # ======================================================================================
    survey_rows.append({
        "type": "begin_group",
        "name": "p4_percepcion_comercio",
        "label": "Percepción ciudadana de seguridad en el comercio",
        "appearance": "field-list",
        "relevant": rel_si
    })

    # 7
    survey_rows.append({
        "type": "select_one seguridad_5",
        "name": "p7_seguridad_entorno_comercial",
        "label": "7. ¿Qué tan seguro percibe usted el entorno de la zona comercial?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })

    add_note(
        "p7_nota",
        "Nota: La respuesta es de selección única.",
        relevant=rel_si
    )

    # 7.1 Condicional: si 7 = Muy inseguro o Inseguro
    rel_71 = (
        f"({rel_si}) and ("
        f"${{p7_seguridad_entorno_comercial}}='{slugify_name('Muy inseguro')}' or "
        f"${{p7_seguridad_entorno_comercial}}='{slugify_name('Inseguro')}'"
        f")"
    )

    survey_rows.append({
        "type": "select_multiple causas_inseguridad_comercio",
        "name": "p71_causas_inseguridad_comercio",
        "label": "7.1. Indique por qué considera insegura esta zona comercial (Marque todos los que apliquen):",
        "required": "yes",
        "relevant": rel_71
    })

    add_note(
        "p71_nota",
        "Nota: Incluye descriptores (selección múltiple).",
        relevant=rel_71
    )

    # 7.1 Otro (detalle)
    survey_rows.append({
        "type": "text",
        "name": "p71_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_71}) and selected(${{p71_causas_inseguridad_comercio}}, '{slugify_name('Otro')}')"
    })

    # 8
    survey_rows.append({
        "type": "select_one escala_1_5",
        "name": "p8_comparacion_anno",
        "label": "8. ¿Cómo se percibe usted la seguridad en la zona comercial este año en comparación con el año anterior?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })

    add_note(
        "p8_nota",
        "Nota: Se utiliza una escala ordinal de 1 a 5.",
        relevant=rel_si
    )

    # 8.1 Condicional (según nota: cuando se selecciona 1,2,3,4 o 5)
    rel_81 = (
        f"({rel_si}) and ("
        f"${{p8_comparacion_anno}}='{slugify_name('1 (Mucho Menos Seguro)')}' or "
        f"${{p8_comparacion_anno}}='{slugify_name('2 (Menos Seguro)')}' or "
        f"${{p8_comparacion_anno}}='{slugify_name('3 (Se mantiene igual)')}' or "
        f"${{p8_comparacion_anno}}='{slugify_name('4 (Más Seguro)')}' or "
        f"${{p8_comparacion_anno}}='{slugify_name('5 (Mucho Más Seguro)')}'"
        f")"
    )

    survey_rows.append({
        "type": "text",
        "name": "p81_indique_por_que",
        "label": "8.1. Indique por qué (Espacio abierto para detallar):",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_81
    })

    # 9 Matriz
    add_note(
        "p9_instr",
        "9. Indique qué tan seguros percibe, en términos de seguridad, los siguientes espacios de la zona comercial:\n"
        "(Usar matriz de selección única por fila con la escala 1 a 5.)",
        relevant=rel_si
    )

    matriz_filas = [
        ("p9_afuera_comercio", "Afuera del comercio"),
        ("p9_pasillos_aceras", "Pasillos / aceras comerciales"),
        ("p9_parqueos", "Parqueos"),
        ("p9_paradas_bus", "Paradas de bus"),
        ("p9_calles_cercanas", "Calles cercanas"),
        ("p9_deficiencia_iluminacion", "Zonas con deficiencia de iluminación"),
    ]

    for nm, lb in matriz_filas:
        survey_rows.append({
            "type": "select_one matriz_1_5_na",
            "name": nm,
            "label": lb,
            "required": "yes",
            "appearance": "minimal",
            "relevant": rel_si
        })

    add_note(
        "p9_nota",
        "Nota: La persona encuestada podrá seleccionar una de las opciones por cada línea de zona.",
        relevant=rel_si
    )

    # 10 Abierta (punto específico)
    survey_rows.append({
        "type": "text",
        "name": "p10_punto_inseguro_motivo",
        "label": "10. Según su percepción, indique si existe algún espacio específico o punto concreto de la zona comercial que perciba como inseguro y explique brevemente el motivo.",
        "required": "yes",
        "appearance": "multiline",
        "relevant": rel_si
    })

    add_note(
        "p10_nota",
        "Nota: La respuesta es de espacio abierto para detallar.",
        relevant=rel_si
    )

    # =========================
    # Glosario Página 4 (si la persona desea)
    # Términos que aparecen en p4: Extorsiones o amenazas / Daños a la propiedad
    # =========================
    survey_rows.append({
        "type": "select_one yesno",
        "name": "p4_accede_glosario",
        "label": "¿Desea acceder al glosario de esta sección?",
        "required": "no",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_glos_p4 = f"({rel_si}) and (${{p4_accede_glosario}}='{v_si}')"

    survey_rows.append({
        "type": "begin_group",
        "name": "p4_glosario",
        "label": "Glosario",
        "relevant": rel_glos_p4
    })
    add_note("p4_glos_intro", "A continuación, se muestran definiciones de términos que aparecen en esta sección.", relevant=rel_glos_p4)
    add_note("p4_glos_extorsion", GLOSARIO_DEFINICIONES["Extorsión"], relevant=rel_glos_p4)
    add_note("p4_glos_danos", GLOSARIO_DEFINICIONES["Daños a la propiedad"], relevant=rel_glos_p4)
    add_note("p4_glos_cierre", "Para continuar con la encuesta, desplácese hacia arriba y continúe con normalidad.", relevant=rel_glos_p4)
    survey_rows.append({"type": "end_group", "name": "p4_glosario_end"})

    survey_rows.append({"type": "end_group", "name": "p4_end"})

    # ======================================================================================
    # PÁGINA 5 — III. RIESGOS, DELITOS, VICTIMIZACIÓN
    # ======================================================================================
    survey_rows.append({
        "type": "begin_group",
        "name": "p5_riesgos_delitos_victim",
        "label": "Riesgos, delitos y victimización",
        "appearance": "field-list",
        "relevant": rel_si
    })

    add_note(
        "p5_titulo_riesgos",
        "III. RIESGOS, DELITOS, VICTIMIZACIÓN\n\nRiesgos sociales y situacionales en la zona comercial",
        relevant=rel_si
    )

    # 11 Horarios inseguridad
    survey_rows.append({
        "type": "select_multiple horarios_inseguridad",
        "name": "p11_horarios_inseguridad",
        "label": "11. ¿En qué horarios percibe mayor inseguridad en la zona comercial donde se ubica su comercio? (Marque todas)",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p11_nota", "Nota: Incluye selección múltiple.", relevant=rel_si)

    # 12 Problemáticas
    survey_rows.append({
        "type": "select_multiple problematicas_comercio",
        "name": "p12_problematicas",
        "label": "12. Seleccione las problemáticas que, según su percepción u observación, afectan la zona comercial donde se ubica su comercio:",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p12_nota", "Nota: Pregunta de selección múltiple.", relevant=rel_si)

    survey_rows.append({
        "type": "text",
        "name": "p12_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p12_problematicas}}, '{slugify_name('Otro')}')"
    })

    # 13 Dónde observado consumo drogas
    survey_rows.append({
        "type": "select_multiple donde_drogas",
        "name": "p13_donde_drogas",
        "label": "13. En relación con el consumo de drogas en el entorno de la zona comercial, indique dónde lo ha observado: (Marque todas las que observe)",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p13_nota", "Nota: Pregunta de selección múltiple.", relevant=rel_si)

    survey_rows.append({
        "type": "text",
        "name": "p13_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p13_donde_drogas}}, '{slugify_name('Otro')}')"
    })

    # 14 Infra vial
    survey_rows.append({
        "type": "select_multiple infra_vial",
        "name": "p14_infra_vial",
        "label": "14. Indique las principales deficiencias de infraestructura vial que afectan el entorno de la zona comercial:",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p14_nota", "Nota: Pregunta de selección múltiple.", relevant=rel_si)

    survey_rows.append({
        "type": "text",
        "name": "p14_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p14_infra_vial}}, '{slugify_name('Otro')}')"
    })

    # 15 Transporte
    survey_rows.append({
        "type": "select_multiple transporte_afect",
        "name": "p15_transporte",
        "label": "15. En relación con el transporte en la zona comercial, indique cuáles situaciones representan una afectación: (Marque todos los que representen afectación)",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p15_nota", "Nota: Selección múltiple.", relevant=rel_si)

    survey_rows.append({
        "type": "text",
        "name": "p15_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p15_transporte}}, '{slugify_name('Otro')}')"
    })

    # 16 Presencia policial
    survey_rows.append({
        "type": "select_multiple presencia_policial_comercio",
        "name": "p16_presencia_policial",
        "label": "16. En relación con la presencia policial en la zona comercial, indique cuál(es) de las siguientes situaciones identifica:",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p16_nota", "Nota: esta pregunta es de selección múltiple.", relevant=rel_si)

    survey_rows.append({
        "type": "text",
        "name": "p16_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p16_presencia_policial}}, '{slugify_name('Otro')}')"
    })

    # ---- Delitos (intro) ----
    add_note(
        "p17_intro",
        "Delitos\n\nA continuación, se presentará una lista de delitos y situaciones delictivas para que seleccione "
        "aquellos que, según su percepción u observación, considera que se presentan en la zona comercial. "
        "Es importante aclarar que no es necesario haber sido víctima ni que la información corresponda a hechos confirmados.",
        relevant=rel_si
    )

    # 17 Delitos (multi)
    survey_rows.append({
        "type": "select_multiple delitos_comercio",
        "name": "p17_delitos",
        "label": "17. Selección múltiple de delitos:",
        "required": "yes",
        "relevant": rel_si
    })
    add_note(
        "p17_nota",
        "Nota: esta pregunta es de selección múltiple, se engloban estos delitos en una sola pregunta ya que ninguno de ellos se subdivide.",
        relevant=rel_si
    )

    survey_rows.append({
        "type": "text",
        "name": "p17_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p17_delitos}}, '{slugify_name('Otro')}')"
    })

    # 18 Manifestación drogas
    survey_rows.append({
        "type": "select_multiple manifest_drogas",
        "name": "p18_manifestacion_drogas",
        "label": "18. Según su percepción u observación, indique de qué forma se manifiesta la presencia de consumo o venta de drogas en el entorno de la zona comercial:",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p18_nota", "Nota: esta pregunta es de selección múltiple.", relevant=rel_si)

    survey_rows.append({
        "type": "text",
        "name": "p18_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p18_manifestacion_drogas}}, '{slugify_name('Otro')}')"
    })

    # 19 Tipos de asaltos
    survey_rows.append({
        "type": "select_multiple asaltos_tipo",
        "name": "p19_tipos_asaltos",
        "label": "19. Según su percepción u observación, indique qué tipos de asaltos considera que ocurren en la zona comercial:",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p19_nota", "Nota: esta pregunta es de selección múltiple.", relevant=rel_si)

    survey_rows.append({
        "type": "text",
        "name": "p19_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p19_tipos_asaltos}}, '{slugify_name('Otro')}')"
    })

    # 20 Estafas
    survey_rows.append({
        "type": "select_multiple estafas_comercio",
        "name": "p20_estafas",
        "label": "20. Estafas que afectan al comercio",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p20_nota", "Nota: esta pregunta es de selección múltiple.", relevant=rel_si)

    survey_rows.append({
        "type": "text",
        "name": "p20_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p20_estafas}}, '{slugify_name('Otro')}')"
    })

    # 21 Robos con fuerza
    survey_rows.append({
        "type": "select_multiple robos_fuerza",
        "name": "p21_robos_fuerza",
        "label": "21. Según su percepción u observación, indique cuáles de los siguientes robos con fuerza considera que afectan a los comercios o su entorno inmediato:",
        "required": "yes",
        "relevant": rel_si
    })
    add_note("p21_nota", "Nota: esta pregunta es de selección múltiple.", relevant=rel_si)

    survey_rows.append({
        "type": "text",
        "name": "p21_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_si}) and selected(${{p21_robos_fuerza}}, '{slugify_name('Otro')}')"
    })

    # ---- Victimización (intro) ----
    add_note(
        "p22_intro",
        "Victimización\n\nA continuación, se presentará una lista de situaciones o hechos para que seleccione aquellos en los que "
        "su local comercial, o personas vinculadas a su actividad comercial, hayan sido directamente afectados en su zona comercial "
        "durante el último año. La información recopilada se utiliza con fines de análisis preventivo y no sustituye una denuncia formal.",
        relevant=rel_si
    )

    # 22
    survey_rows.append({
        "type": "select_one victim_22",
        "name": "p22_afectado_delito",
        "label": "22. Durante los últimos 12 meses, ¿su local comercial fue afectado por algún delito?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_si
    })

    add_note(
        "p22_nota",
        "Nota: la respuesta es de selección única. En el caso que la persona encuestada seleccione la opción “NO” pasar a la pregunta 24. "
        "En caso de contestar “Sí, y denuncié” se habilita la pregunta 22.1, 22.3 y 23. "
        "En el caso que la persona encuestada seleccione la opción “Sí, pero no denuncié” se habilita la pregunta 22.1, 22.2, 22.3 y 23.",
        relevant=rel_si
    )

    rel_22_si_denuncio = f"({rel_si}) and (${{p22_afectado_delito}}='{slugify_name('Sí, y denuncié')}')"
    rel_22_si_no_denuncio = f"({rel_si}) and (${{p22_afectado_delito}}='{slugify_name('Sí, pero no denuncié')}')"
    rel_22_si_cualquiera = f"({rel_si}) and (${{p22_afectado_delito}}='{slugify_name('Sí, y denuncié')}' or ${{p22_afectado_delito}}='{slugify_name('Sí, pero no denuncié')}')"

    # 22.1
    survey_rows.append({
        "type": "select_multiple delitos_afectacion",
        "name": "p221_delitos_afectacion",
        "label": "22.1 ¿Cuál fue el delito por el cual su local comercial o personas vinculadas a su actividad comercial resultaron directamente afectadas?",
        "required": "yes",
        "relevant": rel_22_si_cualquiera
    })
    add_note("p221_nota", "Nota: Esta es una pregunta de selección múltiple.", relevant=rel_22_si_cualquiera)

    survey_rows.append({
        "type": "text",
        "name": "p221_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_22_si_cualquiera}) and selected(${{p221_delitos_afectacion}}, '{slugify_name('Otro')}')"
    })

    # 22.2 (solo si NO denunció)
    survey_rows.append({
        "type": "select_multiple motivo_no_denuncia",
        "name": "p222_motivo_no_denuncia",
        "label": "22.2 En caso de NO haber realizado la denuncia ante el OIJ, indique ¿cuál fue el motivo?",
        "required": "yes",
        "relevant": rel_22_si_no_denuncio
    })
    add_note("p222_nota", "Nota: esta pregunta es de selección múltiple.", relevant=rel_22_si_no_denuncio)

    # 22.3 horario (sí denunció o no denunció)
    survey_rows.append({
        "type": "select_one horario_hecho",
        "name": "p223_horario_hecho",
        "label": "22.3 ¿Tiene conocimiento del horario en el cual se presentó el hecho delictivo que afectó a su local comercial o a personas vinculadas a su actividad comercial?",
        "required": "yes",
        "appearance": "minimal",
        "relevant": rel_22_si_cualquiera
    })
    add_note("p223_nota", "Nota: esta pregunta es de selección única.", relevant=rel_22_si_cualquiera)

    # 23 modo (sí denunció o no denunció)
    survey_rows.append({
        "type": "select_multiple modo_ocurrio",
        "name": "p23_modo_ocurrio",
        "label": "23. ¿Cuál fue la forma o modo en que ocurrió la situación que afectó a su local comercial?",
        "required": "yes",
        "relevant": rel_22_si_cualquiera
    })
    add_note("p23_nota", "Nota: esta pregunta es de selección múltiple.", relevant=rel_22_si_cualquiera)

    survey_rows.append({
        "type": "text",
        "name": "p23_otro_detalle",
        "label": "Otro (detalle):",
        "required": "no",
        "appearance": "multiline",
        "relevant": f"({rel_22_si_cualquiera}) and selected(${{p23_modo_ocurrio}}, '{slugify_name('Otro')}')"
    })

    # 23.1 Incidentes operación
    survey_rows.append({
        "type": "select_multiple incidentes_operacion",
        "name": "p231_incidentes_operacion",
        "label": "23.1 Incidentes de seguridad asociados a la operación del comercio",
        "required": "yes",
        "relevant": rel_si
    })
    add_note(
        "p231_nota_texto",
        "Estos incidentes no necesariamente constituyen delitos, pero afectan la seguridad y el funcionamiento del comercio.\n\n"
        "Nota: esta pregunta es de selección múltiple.",
        relevant=rel_si
    )

    # =========================
    # Glosario Página 5 (si la persona desea)
    # Términos típicos p5: Extorsión / Daños a la propiedad / Receptación / Contrabando / Búnker / Tacha / Ganzúa / Arrebato / Boquete
    # =========================
    survey_rows.append({
        "type": "select_one yesno",
        "name": "p5_accede_glosario",
        "label": "¿Desea acceder al glosario de esta sección?",
        "required": "no",
        "appearance": "minimal",
        "relevant": rel_si
    })
    rel_glos_p5 = f"({rel_si}) and (${{p5_accede_glosario}}='{v_si}')"

    survey_rows.append({
        "type": "begin_group",
        "name": "p5_glosario",
        "label": "Glosario",
        "relevant": rel_glos_p5
    })
    add_note("p5_glos_intro", "A continuación, se muestran definiciones de términos que aparecen en esta sección.", relevant=rel_glos_p5)
    add_note("p5_glos_extorsion", GLOSARIO_DEFINICIONES["Extorsión"], relevant=rel_glos_p5)
    add_note("p5_glos_danos", GLOSARIO_DEFINICIONES["Daños a la propiedad"], relevant=rel_glos_p5)
    add_note("p5_glos_receptacion", GLOSARIO_DEFINICIONES["Receptación"], relevant=rel_glos_p5)
    add_note("p5_glos_contrabando", GLOSARIO_DEFINICIONES["Contrabando"], relevant=rel_glos_p5)
    add_note("p5_glos_bunker", GLOSARIO_DEFINICIONES["Búnker"], relevant=rel_glos_p5)
    add_note("p5_glos_tacha", GLOSARIO_DEFINICIONES["Tacha"], relevant=rel_glos_p5)
    add_note("p5_glos_ganzua", GLOSARIO_DEFINICIONES["Ganzúa"], relevant=rel_glos_p5)
    add_note("p5_glos_arrebato", GLOSARIO_DEFINICIONES["Arrebato"], relevant=rel_glos_p5)
    add_note("p5_glos_boquete", GLOSARIO_DEFINICIONES["Boquete"], relevant=rel_glos_p5)
    add_note("p5_glos_cierre", "Para continuar con la encuesta, desplácese hacia arriba y continúe con normalidad.", relevant=rel_glos_p5)
    survey_rows.append({"type": "end_group", "name": "p5_glosario_end"})

    survey_rows.append({"type": "end_group", "name": "p5_end"})

    # ======================================================================================
    # PÁGINA 6 — (Se completa en Parte 4 junto con exportación y UI final)
    # ======================================================================================

    # =========================
    # DataFrames (preparación)
    # =========================
    survey_cols = [
        "type", "name", "label", "required", "appearance",
        "relevant", "choice_filter",
        "constraint", "constraint_message",
        "media::image",
        "bind::esri:fieldType"
    ]
    df_survey = pd.DataFrame(survey_rows, columns=survey_cols).fillna("")

    # choices: incluir columnas extra si existen (canton_key, any)
    choices_cols_all = set()
    for r in choices_rows:
        choices_cols_all.update(r.keys())
    base_choice_cols = ["list_name", "name", "label"]
    for extra in sorted(choices_cols_all):
        if extra not in base_choice_cols:
            base_choice_cols.append(extra)
    df_choices = pd.DataFrame(choices_rows, columns=base_choice_cols).fillna("")

    df_settings = pd.DataFrame([{
        "form_title": form_title,
        "version": version,
        "default_language": idioma,
        "style": "pages"
    }], columns=["form_title", "version", "default_language", "style"]).fillna("")

    return df_survey, df_choices, df_settings


# ==========================================================================================
# (PARTE 4 continúa): Página 6 completa (24..34) + exportación + vista previa + descargas
# ==========================================================================================
# ==========================================================================================
# ============================== PARTE 4/4 =================================
# ======= Página 6 (24..34) + Exportación completa + UI Construcción =========
# ==========================================================================================

def _agregar_pagina_6_y_exportar():
    st.markdown("---")
    st.subheader("📦 Generar XLSForm (Survey123)")

    idioma = st.selectbox("Idioma (default_language)", options=["es", "en"], index=0)
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión (settings.version)", value=version_auto)

    if st.button("🧮 Construir XLSForm", use_container_width=True):
        # Validación mínima: que exista al menos un cantón y un distrito
        has_canton = any(
            r.get("list_name") == "list_canton" and r.get("name") not in ("__pick_canton__",)
            for r in st.session_state.choices_ext_rows
        )
        has_distrito = any(
            r.get("list_name") == "list_distrito" and r.get("name") not in ("__pick_distrito__",)
            for r in st.session_state.choices_ext_rows
        )

        if not has_canton or not has_distrito:
            st.warning(
                "Aún no has cargado catálogo Cantón→Distrito. Puedes construir igual, "
                "pero en Survey123 verás solo placeholders."
            )

        # =============================
        # 1) Construimos hasta Página 5
        # =============================
        df_survey, df_choices, df_settings = construir_xlsform_completo(
            form_title=form_title,
            logo_media_name=logo_media_name,
            idioma=idioma,
            version=version.strip() or version_auto
        )

        # =============================
        # 2) Agregar Página 6 (24..34)
        # =============================
        # Vamos a añadir filas al df_survey directamente (manteniendo el mismo esquema de columnas)
        # Para ello trabajamos sobre la lista 'survey_rows' original: reconstruimos completo y extendemos.
        # (Se hace así para no perder consistencia con el flujo)
        survey_rows = df_survey.to_dict("records")
        # NOTA: df_survey viene con todas las columnas; al volver a dict es seguro.

        # Helpers para notes sin columnas
        def add_note_row(name, label, relevant=None):
            row = {
                "type": "note",
                "name": name,
                "label": label,
                "bind::esri:fieldType": "null",
                "required": "",
                "appearance": "",
                "choice_filter": "",
                "constraint": "",
                "constraint_message": "",
                "media::image": "",
                "relevant": relevant or ""
            }
            survey_rows.append(row)

        # Helper para agregar preguntas
        def add_q(row: dict):
            # Normaliza columnas para que no falte nada
            base = {
                "type": "", "name": "", "label": "", "required": "", "appearance": "",
                "relevant": "", "choice_filter": "",
                "constraint": "", "constraint_message": "",
                "media::image": "",
                "bind::esri:fieldType": ""
            }
            base.update(row)
            survey_rows.append(base)

        rel_si = f"${{acepta_participar}}='{slugify_name('Sí')}'"

        # Relevants para saltos desde victimización
        rel_p22_no = f"({rel_si}) and (${{p22_afectado_delito}}='{slugify_name('No')}')"

        # =============================
        # Página 6: begin_group
        # =============================
        add_q({
            "type": "begin_group",
            "name": "p6_mejora_confianza_programa_contacto",
            "label": "Acciones sugeridas, confianza y contacto",
            "appearance": "field-list",
            "relevant": rel_si
        })

        add_note_row(
            "p6_intro",
            "IV. ACCIONES Y MEJORAS PARA LA SEGURIDAD COMERCIAL\n\n"
            "A continuación, se presentan preguntas orientadas a identificar acciones sugeridas para mejorar la seguridad en la zona comercial, "
            "valoración del servicio policial, conocimiento de programas preventivos y opciones de contacto (voluntario).",
            relevant=rel_si
        )

        # 24 Fuerza Pública (multi)
        add_q({
            "type": "select_multiple act_fp",
            "name": "p24_acciones_fp",
            "label": "24. Seleccione las acciones o mejoras que considera necesarias por parte de Fuerza Pública para mejorar la seguridad en la zona comercial: (Marque todas)",
            "required": "yes",
            "relevant": rel_si
        })
        add_note_row("p24_nota", "Nota: Pregunta de selección múltiple. Incluye la opción “No indica”.", relevant=rel_si)
        add_q({
            "type": "text",
            "name": "p24_otro_detalle",
            "label": "Otro (detalle):",
            "required": "no",
            "appearance": "multiline",
            "relevant": f"({rel_si}) and selected(${{p24_acciones_fp}}, '{slugify_name('Otro')}')"
        })

        # 25 Municipalidad (multi)
        add_q({
            "type": "select_multiple act_muni",
            "name": "p25_acciones_municipalidad",
            "label": "25. Seleccione las acciones o mejoras que considera necesarias por parte de la Municipalidad para mejorar la seguridad en la zona comercial: (Marque todas)",
            "required": "yes",
            "relevant": rel_si
        })
        add_note_row("p25_nota", "Nota: Pregunta de selección múltiple. Incluye la opción “No indica”.", relevant=rel_si)
        add_q({
            "type": "text",
            "name": "p25_otro_detalle",
            "label": "Otro (detalle):",
            "required": "no",
            "appearance": "multiline",
            "relevant": f"({rel_si}) and selected(${{p25_acciones_municipalidad}}, '{slugify_name('Otro')}')"
        })

        # 26 Servicio policial 24 meses (única)
        add_q({
            "type": "select_one servicio_24m",
            "name": "p26_servicio_24m",
            "label": "26. En los últimos 24 meses, ¿cómo considera que ha sido el servicio de Fuerza Pública en esta zona comercial?",
            "required": "yes",
            "appearance": "minimal",
            "relevant": rel_si
        })
        add_note_row("p26_nota", "Nota: Pregunta de selección única.", relevant=rel_si)

        # 27 Conoce policías (sí/no)
        add_q({
            "type": "select_one yesno",
            "name": "p27_conoce_policias",
            "label": "27. ¿Conoce policías de Fuerza Pública que se desempeñen en esta zona comercial?",
            "required": "yes",
            "appearance": "minimal",
            "relevant": rel_si
        })
        add_note_row("p27_nota", "Nota: Pregunta de selección única.", relevant=rel_si)

        # 28 Conoce programa
        add_q({
            "type": "select_one yesno",
            "name": "p28_conoce_programa",
            "label": "28. ¿Conoce el Programa de Seguridad Comercial implementado en su distrito?",
            "required": "yes",
            "appearance": "minimal",
            "relevant": rel_si
        })
        add_note_row("p28_nota", "Nota: Pregunta de selección única.", relevant=rel_si)

        # 29 Inscrito (si 28=Sí)
        rel_29 = f"({rel_si}) and (${{p28_conoce_programa}}='{slugify_name('Sí')}')"
        add_q({
            "type": "select_one yesno",
            "name": "p29_inscrito_programa",
            "label": "29. ¿Su comercio está inscrito o participa actualmente en el Programa de Seguridad Comercial?",
            "required": "yes",
            "appearance": "minimal",
            "relevant": rel_29
        })
        add_note_row("p29_nota", "Nota: Pregunta de selección única (se habilita si respondió “Sí” en la pregunta 28).", relevant=rel_29)

        # 30 Desea contacto (si 28=No o 29=No)
        # (Se mantiene lógica inclusiva: si no conoce programa o si conoce pero no está inscrito)
        rel_30 = (
            f"({rel_si}) and ("
            f"${{p28_conoce_programa}}='{slugify_name('No')}' or "
            f"(${{p28_conoce_programa}}='{slugify_name('Sí')}' and ${{p29_inscrito_programa}}='{slugify_name('No')}')"
            f")"
        )
        add_q({
            "type": "select_one yesno",
            "name": "p30_desea_contacto_programa",
            "label": "30. ¿Desea que se le contacte para brindarle información sobre el Programa de Seguridad Comercial?",
            "required": "yes",
            "appearance": "minimal",
            "relevant": rel_30
        })
        add_note_row("p30_nota", "Nota: Pregunta de selección única.", relevant=rel_30)

        # 31 Datos de contacto (si 30=Sí) — voluntario pero requerido dentro del bloque
        rel_31 = f"({rel_30}) and (${{p30_desea_contacto_programa}}='{slugify_name('Sí')}')"

        add_q({
            "type": "text",
            "name": "p31_nombre_contacto",
            "label": "31.1 Nombre (opcional):",
            "required": "no",
            "relevant": rel_31
        })
        add_q({
            "type": "text",
            "name": "p31_telefono_contacto",
            "label": "31.2 Teléfono:",
            "required": "yes",
            "relevant": rel_31
        })
        add_q({
            "type": "text",
            "name": "p31_correo_contacto",
            "label": "31.3 Correo electrónico:",
            "required": "no",
            "relevant": rel_31
        })
        add_note_row(
            "p31_nota",
            "Nota: Los datos de contacto se solicitan únicamente si la persona encuestada desea ser contactada. "
            "El suministro de información personal es voluntario, salvo el medio mínimo para contactarle (teléfono) cuando así lo solicita.",
            relevant=rel_31
        )

        # 32 Información sobre persona/grupo que genera delito (sí/no)
        add_q({
            "type": "select_one yesno",
            "name": "p32_info_grupo_delito",
            "label": "32. ¿Tiene información sobre alguna persona o grupo que genere delitos o situaciones de inseguridad en la zona comercial?",
            "required": "yes",
            "appearance": "minimal",
            "relevant": rel_si
        })
        add_note_row("p32_nota", "Nota: Pregunta de selección única. No constituye denuncia formal.", relevant=rel_si)

        # 33 Detalle (si 32=Sí)
        rel_33 = f"({rel_si}) and (${{p32_info_grupo_delito}}='{slugify_name('Sí')}')"
        add_q({
            "type": "text",
            "name": "p33_detalle_info",
            "label": "33. Detalle la información (de forma general):",
            "required": "yes",
            "appearance": "multiline",
            "relevant": rel_33
        })
        add_note_row(
            "p33_nota",
            "Nota: No incluya datos sensibles innecesarios. La información se utiliza con fines preventivos y estadísticos.",
            relevant=rel_33
        )

        # 34 Cierre (nota)
        add_note_row(
            "p34_cierre",
            "34. Fin de la encuesta.\n\nMuchas gracias por su colaboración. Su participación contribuirá al fortalecimiento de la seguridad en la zona comercial.",
            relevant=rel_si
        )

        # Glosario Página 6 (solo si desea) — aplica si se mencionan términos de glosario en esta página (generalmente ninguno)
        # Lo dejamos disponible pero solo mostrando definiciones si se desea; aquí incluimos “Extorsión” y “Receptación”
        # como apoyo, dado que el bloque 32-33 puede tocar temas asociados.
        add_q({
            "type": "select_one yesno",
            "name": "p6_accede_glosario",
            "label": "¿Desea acceder al glosario de esta sección?",
            "required": "no",
            "appearance": "minimal",
            "relevant": rel_si
        })
        rel_glos_p6 = f"({rel_si}) and (${{p6_accede_glosario}}='{slugify_name('Sí')}')"
        add_q({
            "type": "begin_group",
            "name": "p6_glosario",
            "label": "Glosario",
            "relevant": rel_glos_p6
        })
        add_note_row("p6_glos_intro", "A continuación, se muestran definiciones de términos relacionados que pueden aparecer en la encuesta.", relevant=rel_glos_p6)
        add_note_row("p6_glos_extorsion", GLOSARIO_DEFINICIONES["Extorsión"], relevant=rel_glos_p6)
        add_note_row("p6_glos_receptacion", GLOSARIO_DEFINICIONES["Receptación"], relevant=rel_glos_p6)
        add_note_row("p6_glos_cierre", "Para continuar con la encuesta, desplácese hacia arriba y continúe con normalidad.", relevant=rel_glos_p6)
        add_q({"type": "end_group", "name": "p6_glosario_end"})

        # end_group página 6
        add_q({"type": "end_group", "name": "p6_end"})

        # =============================
        # 3) Reconstruir df_survey final
        # =============================
        survey_cols = [
            "type", "name", "label", "required", "appearance",
            "relevant", "choice_filter",
            "constraint", "constraint_message",
            "media::image",
            "bind::esri:fieldType"
        ]
        df_survey_final = pd.DataFrame(survey_rows, columns=survey_cols).fillna("")

        # =============================
        # 4) Vista previa y descarga
        # =============================
        st.success("XLSForm construido. Vista previa rápida:")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Hoja: survey**")
            st.dataframe(df_survey_final, use_container_width=True, hide_index=True)
        with c2:
            st.markdown("**Hoja: choices**")
            st.dataframe(df_choices, use_container_width=True, hide_index=True)
        with c3:
            st.markdown("**Hoja: settings**")
            st.dataframe(df_settings, use_container_width=True, hide_index=True)

        nombre_archivo = slugify_name(form_title) + "_xlsform.xlsx"
        descargar_xlsform(df_survey_final, df_choices, df_settings, nombre_archivo)

        # Logo para carpeta media/
        if st.session_state.get("_logo_bytes"):
            st.download_button(
                "📥 Descargar logo para carpeta media/",
                data=st.session_state["_logo_bytes"],
                file_name=logo_media_name,
                mime="image/png",
                use_container_width=True
            )

        st.info("""
**Cómo usar en Survey123 Connect**
1) Crear encuesta **desde archivo** y seleccionar el XLSForm descargado.  
2) Copiar el logo dentro de la carpeta **media/** del proyecto, con el **mismo nombre** que pusiste en `media::image`.  
3) Verás páginas con **Siguiente/Anterior** (porque `settings.style = pages`).  
4) Los glosarios aparecen solo si la persona marca **Sí** (no es obligatorio).  
5) Las **notas** no generarán columnas vacías en la tabla (porque usan `bind::esri:fieldType = null`).  
""")

# ==========================================================================================
# Llamada final para activar el flujo de exportación dentro de la app
# ==========================================================================================
_agregar_pagina_6_y_exportar()


