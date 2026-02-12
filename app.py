# ============================== PARTE 1 / 4 ==============================
# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Encuesta COMERCIO → XLSForm para ArcGIS Survey123 (versión extendida)
# - Constructor completo (agregar/editar/ordenar/borrar)
# - Condicionales (relevant) + finalizar temprano
# - Listas en cascada (choice_filter) Cantón→Distrito [CATÁLOGO MANUAL POR LOTES]
# - Exportar/Importar proyecto (JSON)
# - Exportar a XLSForm (survey/choices/settings)
# - PÁGINAS reales (style="pages"): Intro + Consentimiento + P2.. (por secciones)
# - Portada con logo (media::image) y texto de introducción
# - Consentimiento:
#     - Texto en BLOQUES (notes separados) para que se vea ordenado en Survey123
#     - Si marca "No" ⇒ NO muestra el resto de páginas y cae a una página final para enviar
# - FIX: no mostrar placeholders "— escoja un cantón —" cuando ya hay catálogo real
# - FIX MATRIZ (table-list): todas las filas comparten el MISMO list_name (list_override)
# - FIX: Opciones "No se observa / No se observan ..." en select_multiple son EXCLUSIVAS
# - FIX REFLEJO DE EDICIÓN: qid estable por pregunta (editor deja de depender del índice)
#
# ✅ Versión COMERCIO (limpia / actualizada):
#   - Intro Comercio + Consentimiento (igual estructura)
#   - Datos demográficos: Cantón, Distrito, Edad, Género, Escolaridad
#   - + Pregunta 6: Tipo de local comercial (select_one + Otro texto)
#   - II Percepción comercio: 7, 7.1 (+Otro), 8, 8.1, 9 Matriz, 10 (+Otro), 11
#   - III Riesgos: 12 (+Otro), 13 (+Otro), 14 (+Otro), 15 (+Otro), 16
#   - Delitos: 17 (+Otro), 18 (+Otro), 19 (+Otro), 20 (+Otro), 21
#
# ✅ Nota sobre nombre del archivo XLSForm descargado:
#   - Ahora el nombre se arma SIEMPRE con el texto actual de “Delegación/Lugar” (no queda “pegado”).
# ==========================================================================================

import re
import json
import uuid
from io import BytesIO
from datetime import datetime
from typing import List, Dict

import streamlit as st
import pandas as pd

# ------------------------------------------------------------------------------------------
# Configuración de la app
# ------------------------------------------------------------------------------------------
st.set_page_config(page_title="Encuesta Comercio → XLSForm (Survey123)", layout="wide")
st.title("🏪 Encuesta Comercio → XLSForm para ArcGIS Survey123")

st.markdown("""
Crea tu cuestionario y **exporta un XLSForm** listo para **ArcGIS Survey123**.

Incluye:
- Tipos: **text**, **integer/decimal**, **date**, **time**, **geopoint**, **select_one**, **select_multiple**.
- **Constructor completo** (agregar, editar, ordenar, borrar) con condicionales.
- **Listas en cascada** **Cantón→Distrito** (**catálogo manual por lotes**).
- **Páginas** con navegación **Siguiente/Anterior** (`settings.style = pages`).
- **Portada** con **logo** (`media::image`) e **introducción**.
- **Consentimiento informado** (si NO acepta, la encuesta termina) con texto ordenado por bloques.
""")

# ------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------
TIPOS = [
    "Texto (corto)",
    "Párrafo (texto largo)",
    "Número",
    "Selección única",
    "Selección múltiple",
    "Fecha",
    "Hora",
    "GPS (ubicación)",
]

def _rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

def slugify_name(texto: str) -> str:
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

def map_tipo_to_xlsform(tipo_ui: str, name: str):
    if tipo_ui == "Texto (corto)":
        return ("text", None, None)
    if tipo_ui == "Párrafo (texto largo)":
        return ("text", "multiline", None)
    if tipo_ui == "Número":
        return ("integer", None, None)
    if tipo_ui == "Selección única":
        return (f"select_one list_{name}", None, f"list_{name}")
    if tipo_ui == "Selección múltiple":
        return (f"select_multiple list_{name}", None, f"list_{name}")
    if tipo_ui == "Fecha":
        return ("date", None, None)
    if tipo_ui == "Hora":
        return ("time", None, None)
    if tipo_ui == "GPS (ubicación)":
        return ("geopoint", None, None)
    return ("text", None, None)

def xlsform_or_expr(conds):
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return "(" + " or ".join(conds) + ")"

def xlsform_not(expr):
    if not expr:
        return None
    return f"not({expr})"

def build_relevant_expr(rules_for_target: List[Dict]):
    or_parts = []
    for r in rules_for_target:
        src = r["src"]
        op = r.get("op", "=")
        vals = r.get("values", [])
        if not vals:
            continue

        if op == "=":
            segs = [f"${{{src}}}='{v}'" for v in vals]
        elif op == "selected":
            segs = [f"selected(${{{src}}}, '{v}')" for v in vals]
        elif op == "!=":
            segs = [f"${{{src}}}!='{v}'" for v in vals]
        else:
            segs = [f"${{{src}}}='{v}'" for v in vals]

        or_parts.append(xlsform_or_expr(segs))
    return xlsform_or_expr(or_parts)

# ------------------------------------------------------------------------------------------
# FIX REFLEJO DE EDICIÓN: ID estable por pregunta (qid) + editor por qid
# ------------------------------------------------------------------------------------------
def ensure_qid(q: Dict) -> Dict:
    if "qid" not in q or not q["qid"]:
        q["qid"] = str(uuid.uuid4())
    return q

def q_index_by_qid(qid: str) -> int:
    for i, q in enumerate(st.session_state.preguntas):
        if q.get("qid") == qid:
            return i
    return -1

# ------------------------------------------------------------------------------------------
# Estado base (session_state)
# ------------------------------------------------------------------------------------------
if "preguntas" not in st.session_state:
    st.session_state.preguntas = []
if "reglas_visibilidad" not in st.session_state:
    st.session_state.reglas_visibilidad = []
if "reglas_finalizar" not in st.session_state:
    st.session_state.reglas_finalizar = []

# ✅ Textos fijos editables (solo matriz 9)
if "textos_fijos" not in st.session_state:
    st.session_state.textos_fijos = {
        "matriz_9_label": "9. En términos de seguridad, indique qué tan seguros percibe los siguientes espacios alrededor de su comercio."
    }

# Editor: solo una pregunta abierta a la vez (por qid estable)
if "edit_qid" not in st.session_state:
    st.session_state.edit_qid = None

with st.expander("✏️ Textos fijos (editables)", expanded=False):
    st.caption("Esto es para editar textos que NO son preguntas individuales (por ejemplo, encabezados internos como la Matriz 9).")
    st.session_state.textos_fijos["matriz_9_label"] = st.text_input(
        "Texto del encabezado de la Matriz 9",
        value=st.session_state.textos_fijos.get("matriz_9_label", ""),
        key="txt_matriz9"
    )

# ------------------------------------------------------------------------------------------
# Catálogo manual por lotes: Cantón → Distritos
# ------------------------------------------------------------------------------------------
if "choices_ext_rows" not in st.session_state:
    st.session_state.choices_ext_rows = []  # filas para hoja choices
if "choices_extra_cols" not in st.session_state:
    st.session_state.choices_extra_cols = set()

def _append_choice_unique(row: Dict):
    key = (row.get("list_name"), row.get("name"))
    exists = any((r.get("list_name"), r.get("name")) == key for r in st.session_state.choices_ext_rows)
    if not exists:
        st.session_state.choices_ext_rows.append(row)

def _asegurar_placeholders_catalogo():
    """
    Survey123 exige que existan list_canton/list_distrito en choices si se usan en survey.
    Esto garantiza placeholders aun cuando el usuario NO agregue lotes.
    """
    st.session_state.choices_extra_cols.update({"canton_key", "any"})
    _append_choice_unique({"list_name": "list_canton", "name": "__pick_canton__", "label": "— escoja un cantón —"})
    _append_choice_unique({"list_name": "list_distrito", "name": "__pick_distrito__", "label": "— escoja un cantón —", "any": "1"})

def _hay_catalogo_real() -> bool:
    cantones_reales = any(
        r.get("list_name") == "list_canton" and r.get("name") not in (None, "", "__pick_canton__")
        for r in st.session_state.choices_ext_rows
    )
    distritos_reales = any(
        r.get("list_name") == "list_distrito" and r.get("name") not in (None, "", "__pick_distrito__")
        for r in st.session_state.choices_ext_rows
    )
    return bool(cantones_reales and distritos_reales)

def _filtrar_placeholders_si_hay_catalogo(rows: List[Dict]) -> List[Dict]:
    if not _hay_catalogo_real():
        return rows
    filtradas = []
    for r in rows:
        if r.get("list_name") == "list_canton" and r.get("name") == "__pick_canton__":
            continue
        if r.get("list_name") == "list_distrito" and r.get("name") == "__pick_distrito__":
            continue
        filtradas.append(r)
    return filtradas

# Asegurar placeholders desde el inicio
_asegurar_placeholders_catalogo()

st.markdown("### 📚 Catálogo Cantón → Distrito (por lotes)")
with st.expander("Agrega un lote (un Cantón y varios Distritos)", expanded=True):
    col_c1, col_c2 = st.columns(2)
    canton_txt = col_c1.text_input("Cantón (una vez)", value="", key="canton_lote")
    distritos_txt = col_c2.text_area("Distritos del cantón (uno por línea)", value="", height=130, key="distritos_lote")

    col_b1, col_b2, _ = st.columns([1, 1, 2])
    add_lote = col_b1.button("Agregar lote", type="primary", use_container_width=True, key="btn_add_lote")
    clear_all = col_b2.button("Limpiar catálogo", use_container_width=True, key="btn_clear_cat")

    if clear_all:
        st.session_state.choices_ext_rows = []
        st.session_state.choices_extra_cols = set()
        _asegurar_placeholders_catalogo()
        st.success("Catálogo limpiado (placeholders conservados).")
        _rerun()

    if add_lote:
        c = canton_txt.strip()
        distritos = [d.strip() for d in distritos_txt.splitlines() if d.strip()]
        if not c or not distritos:
            st.error("Debes indicar Cantón y al menos un Distrito.")
        else:
            slug_c = slugify_name(c)

            st.session_state.choices_extra_cols.update({"canton_key", "any"})
            _asegurar_placeholders_catalogo()

            _append_choice_unique({"list_name": "list_canton", "name": slug_c, "label": c})

            usados_d = set()
            for d in distritos:
                slug_d = asegurar_nombre_unico(slugify_name(d), usados_d)
                usados_d.add(slug_d)
                _append_choice_unique({"list_name": "list_distrito", "name": slug_d, "label": d, "canton_key": slug_c})

            st.success(f"Lote agregado: {c} → {len(distritos)} distritos.")
            _rerun()

if st.session_state.choices_ext_rows:
    st.dataframe(
        pd.DataFrame(st.session_state.choices_ext_rows),
        use_container_width=True,
        hide_index=True,
        height=240
    )

# ------------------------------------------------------------------------------------------
# Cabecera: Logo + Delegación/Lugar
# ------------------------------------------------------------------------------------------
DEFAULT_LOGO_PATH = "001.png"

col_logo, col_txt = st.columns([1, 3], vertical_alignment="center")
with col_logo:
    up_logo = st.file_uploader("Logo (PNG/JPG)", type=["png", "jpg", "jpeg"], key="uploader_logo")
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
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    delegacion = st.text_input("Nombre del lugar / Delegación", value="Alajuela Norte", key="delegacion_txt")
    logo_media_name = st.text_input(
        "Nombre de archivo para `media::image`",
        value=st.session_state.get("_logo_name", "001.png"),
        help="Debe coincidir con el archivo en `media/` de Survey123 Connect.",
        key="logo_media_txt"
    )
    titulo_compuesto = (f"Encuesta comercio – {delegacion.strip()}" if delegacion.strip() else "Encuesta comercio")
    st.markdown(f"<h5 style='text-align:center;margin:4px 0'>📋 {titulo_compuesto}</h5>", unsafe_allow_html=True)

def _nombre_archivo_xlsform() -> str:
    # ✅ Siempre usa el texto ACTUAL de delegación/lugar (evita que quede “pegado” de una sesión anterior)
    base = slugify_name(f"encuesta_comercio_{delegacion.strip() or 'zona'}_xlsform")
    return f"{base}.xlsx"

# ------------------------------------------------------------------------------------------
# Intro (Página 1)
# ------------------------------------------------------------------------------------------
INTRO_COMERCIO = (
    "El presente formato corresponde a la Encuesta de Percepción de Comercio 2026, diseñada para "
    "recopilar información clave sobre seguridad ciudadana, convivencia y factores de riesgo en los "
    "cantones del territorio nacional. Este documento se remite para su revisión y validación por parte "
    "de las direcciones, departamentos u oficinas con competencia técnica en cada uno de los apartados, "
    "con el fin de asegurar su coherencia metodológica, normativa y operativa con los lineamientos "
    "institucionales vigentes. Las observaciones recibidas permitirán fortalecer el instrumento antes "
    "de su aplicación en territorio."
)

# ------------------------------------------------------------------------------------------
# Consentimiento informado (Página 2) (estructura igual)
# ------------------------------------------------------------------------------------------
CONSENTIMIENTO_TITULO = "Consentimiento Informado para la Participación en la Encuesta"
CONSENT_SI = slugify_name("Sí")
CONSENT_NO = slugify_name("No")

CONSENTIMIENTO_BLOQUES = [
    "Usted está siendo invitado(a) a participar de forma libre y voluntaria en una encuesta sobre seguridad, convivencia y percepción ciudadana, dirigida a personas mayores de 18 años.",
    "El objetivo de esta encuesta es recopilar información de carácter preventivo y estadístico, con el fin de apoyar la planificación de acciones de prevención, mejora de la convivencia y fortalecimiento de la seguridad en comunidades y zonas comerciales.",
    "La participación es totalmente voluntaria. Usted puede negarse a responder cualquier pregunta, así como retirarse de la encuesta en cualquier momento, sin que ello genere consecuencia alguna.",
    "De conformidad con lo dispuesto en el artículo 5 de la Ley N.º 8968 (Protección de la Persona frente al Tratamiento de sus Datos Personales), se le informa que:",
    "Finalidad del tratamiento: La información recopilada será utilizada exclusivamente para fines estadísticos, analíticos y preventivos, y no para investigaciones penales, procesos judiciales, sanciones administrativas ni procedimientos disciplinarios.",
    "Datos personales: Algunos apartados permiten, de forma voluntaria, el suministro de datos personales o información de contacto.",
    "Tratamiento de los datos: Los datos serán almacenados, analizados y resguardados bajo criterios de confidencialidad y seguridad, conforme a la normativa vigente.",
    "Destinatarios y acceso: La información será conocida únicamente por el personal autorizado de la Fuerza Pública / Ministerio de Seguridad Pública, para los fines indicados. No será cedida a terceros ajenos a estos fines.",
    "Responsable de la base de datos: El Ministerio de Seguridad Pública, a través de la Dirección de Programas Policiales Preventivos, Oficina Estrategia Integral de Prevención para la Seguridad Pública (EIPESP / Estrategia Sembremos Seguridad), será responsable del tratamiento y custodia de la información recolectada.",
    "Derechos de la persona participante: Usted conserva el derecho a la autodeterminación informativa y a decidir libremente sobre el suministro de sus datos.",
    "Las respuestas brindadas no constituyen denuncias formales, ni sustituyen los mecanismos legales correspondientes.",
    "Al continuar con la encuesta, usted manifiesta haber leído y comprendido la información anterior y otorga su consentimiento informado para participar."
]

# ------------------------------------------------------------------------------------------
# Textos Intro por página (COMERCIO)
# ------------------------------------------------------------------------------------------
INTRO_DEMOGRAFICOS_COMERCIO = (
    "Con el fin de hacer más segura la zona comercial de este distrito, deseamos concentrarnos en los "
    "problemas de seguridad más importantes que afectan a los negocios. Queremos trabajar en conjunto "
    "con el gobierno local, otras instituciones y las personas comerciantes para reducir los delitos y "
    "riesgos que afectan la actividad comercial.\n\n"
    "Es importante recordarle que la información que usted nos proporcione es confidencial y se utilizará "
    "únicamente para mejorar la seguridad en esta zona comercial."
)

INTRO_PERCEPCION_COMERCIO = (
    "En esta sección le preguntaremos sobre cómo percibe la seguridad en el entorno donde desarrolla su actividad comercial. "
    "Las siguientes preguntas buscan conocer su opinión y experiencia sobre la seguridad en el lugar donde se ubica su negocio, "
    "así como en los espacios cercanos que forman parte de la dinámica comercial.\n\n"
    "Nos interesa saber cómo siente y cómo observa la seguridad en la zona comercial, cuáles situaciones generan mayor o menor "
    "tranquilidad y si considera que la situación ha mejorado, empeorado o se mantiene igual. Sus respuestas nos ayudarán a "
    "identificar qué factores generan preocupación en el comercio y cómo se vive la seguridad desde la actividad económica.\n\n"
    "Esta información se utilizará para apoyar el análisis preventivo del entorno comercial y orientar acciones de mejora y prevención. "
    "No hay respuestas correctas o incorrectas. Le pedimos responder con sinceridad, según su experiencia y percepción personal."
)

INTRO_RIESGOS_COMERCIO = (
    "A continuación, en esta sección le preguntaremos sobre situaciones o condiciones que pueden representar riesgos para la actividad "
    "comercial y la convivencia en la zona. Estas preguntas no se refieren necesariamente a delitos, sino a situaciones, comportamientos "
    "o problemáticas que usted haya observado y que puedan generar preocupación, afectar la operación del comercio o aumentar el riesgo "
    "de que ocurran hechos de inseguridad.\n\n"
    "Nos interesa conocer qué situaciones están presentes en el entorno comercial, con qué frecuencia se observan y en qué espacios se presentan, "
    "según su experiencia y percepción. Sus respuestas ayudarán a identificar factores de riesgo y a orientar acciones preventivas y de articulación local. "
    "No existen respuestas correctas o incorrectas. Le pedimos responder con sinceridad, de acuerdo con lo que ha visto o vivido en su entorno comercial."
)

INTRO_DELITOS_COMERCIO = (
    "A continuación, se presenta una lista de delitos para que indique aquellos que, según su conocimiento u observación, considera que se presentan "
    "en la zona donde desarrolla su actividad comercial. La información recopilada tiene fines de análisis preventivo y territorial y no constituye "
    "una denuncia formal ni la confirmación judicial de hechos delictivos."
)

# ------------------------------------------------------------------------------------------
# Precarga de preguntas (seed) — COMERCIO (limpio)
# ------------------------------------------------------------------------------------------
if "seed_cargado" not in st.session_state:
    v_muy_inseguro = slugify_name("Muy inseguro")
    v_inseguro = slugify_name("Inseguro")

    LISTA_MATRIZ_SEG = "list_matriz_seguridad"
    SLUG_SI = slugify_name("Sí")
    SLUG_NO = slugify_name("No")

    seed = [
        # ---------------- Consentimiento (se mantiene) ----------------
        {"tipo_ui": "Selección única",
         "label": "¿Acepta participar en esta encuesta?",
         "name": "consentimiento",
         "required": True,
         "opciones": ["Sí", "No"],
         "appearance": "horizontal",
         "choice_filter": None,
         "relevant": None},

        # ---------------- I. DATOS DEMOGRÁFICOS (Comercio) ----------------
        {"tipo_ui": "Selección única", "label": "1. Cantón:", "name": "canton", "required": True,
         "opciones": [], "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única", "label": "2. Distrito:", "name": "distrito", "required": True,
         "opciones": [], "appearance": None, "choice_filter": "canton_key=${canton}", "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "3. Edad (en años cumplidos): marque una categoría que incluya su edad.",
         "name": "edad_rango",
         "required": True,
         "opciones": ["18 a 29 años", "30 a 44 años", "45 a 64 años", "65 años o más"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "4. ¿Con cuál de estas opciones se identifica?",
         "name": "genero",
         "required": True,
         "opciones": ["Femenino", "Masculino", "Persona no Binaria", "Prefiero no decir"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "5. Escolaridad:",
         "name": "escolaridad",
         "required": True,
         "opciones": [
             "Ninguna",
             "Primaria incompleta",
             "Primaria completa",
             "Secundaria incompleta",
             "Secundaria completa",
             "Técnico",
             "Universitaria incompleta",
             "Universitaria completa",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "6. Tipo de local comercial",
         "name": "tipo_local_comercial",
         "required": True,
         "opciones": [
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
         ],
         "appearance": "columns",
         "choice_filter": None,
         "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro tipo de local comercial:",
         "name": "tipo_local_otro",
         "required": True,
         "opciones": [],
         "appearance": None,
         "choice_filter": None,
         "relevant": f"${{tipo_local_comercial}}='{slugify_name('Otro')}'"},

        # ---------------- II. PERCEPCIÓN CIUDADANA EN EL COMERCIO ----------------
        {"tipo_ui": "Selección única",
         "label": "7. ¿Qué tan seguro percibe usted el entorno en su local comercial?",
         "name": "percep_seg_local",
         "required": True,
         "opciones": ["Muy inseguro", "Inseguro", "Ni seguro ni inseguro", "Seguro", "Muy seguro"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple",
         "label": "7.1. Indique por qué considera inseguro el entorno del local comercial (Marque todos los que apliquen):",
         "name": "motivos_inseguridad_local",
         "required": True,
         "opciones": [
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
             "Presencia de personas en situación de calle que influye en su percepción de seguridad",
             "Presencia de personas en situación de ocio (sin actividad laboral o educativa)",
             "Intentos de cobro ilegal o exigencias indebidas a comercios",
             "Otro",
         ],
         "appearance": "columns",
         "choice_filter": None,
         "relevant": xlsform_or_expr([
             f"${{percep_seg_local}}='{v_muy_inseguro}'",
             f"${{percep_seg_local}}='{v_inseguro}'"
         ])},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "Indique cuál es ese otro motivo:",
         "name": "motivos_inseguridad_local_otro",
         "required": True,
         "opciones": [],
         "appearance": "multiline",
         "choice_filter": None,
         "relevant": f"selected(${{motivos_inseguridad_local}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección única",
         "label": "8. ¿En comparación con los 12 meses anteriores, cómo percibe que ha cambiado la seguridad en los alrededores del lugar comercial?",
         "name": "cambio_seguridad_12m_comercio",
         "required": True,
         "opciones": ["Mucho menos seguro (1)", "Menos seguro (2)", "Se mantiene igual (3)", "Más seguro (4)", "Mucho más seguro (5)"],
         "appearance": "horizontal", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "8.1. Indique por qué (explique brevemente la razón de su respuesta anterior):",
         "name": "motivo_cambio_12m_comercio",
         "required": True,
         "opciones": [],
         "appearance": "multiline", "choice_filter": None, "relevant": "string-length(${cambio_seguridad_12m_comercio})>0"},

        # 9. MATRIZ (table-list) — alrededor del comercio
        {"tipo_ui": "Selección única", "label": "Afuera del comercio", "name": "m9_afuera_comercio",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_SEG},

        {"tipo_ui": "Selección única", "label": "Pasillos / aceras comerciales", "name": "m9_pasillos_aceras",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_SEG},

        {"tipo_ui": "Selección única", "label": "Parqueos", "name": "m9_parqueos",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_SEG},

        {"tipo_ui": "Selección única", "label": "Paradas de bus", "name": "m9_paradas_bus",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_SEG},

        {"tipo_ui": "Selección única", "label": "Calles cercanas", "name": "m9_calles_cercanas",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_SEG},

        {"tipo_ui": "Selección única",
         "label": "10. Desde su percepción, ¿en qué lugar se concentra principalmente la inseguridad alrededor de su comercio?",
         "name": "foco_inseguridad_comercio",
         "required": True,
         "opciones": [
             "Zonas residenciales cercanas (calles y barrios)",
             "Paradas, estaciones y transporte público",
             "Espacios recreativos (parques y plazas)",
             "Centros educativos",
             "Lugares de entretenimiento (bares, discotecas y similares)",
             "Lugares de interés turístico",
             "Alrededores inmediatos del comercio",
             "Zona bancaria",
             "Otro (especifique)",
         ],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro lugar:",
         "name": "foco_inseguridad_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"${{foco_inseguridad_comercio}}='{slugify_name('Otro (especifique)')}'"},

        {"tipo_ui": "Selección múltiple",
         "label": "11. ¿En qué horarios percibe mayor inseguridad en el entorno comercial donde se ubica su comercio?",
         "name": "horarios_mayor_inseguridad",
         "required": True,
         "opciones": ["Mañana", "Tarde", "Noche", "Madrugada"],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        # ---------------- III. RIESGOS, DELITOS, VICTIMIZACIÓN ----------------
        {"tipo_ui": "Selección múltiple",
         "label": "12. Seleccione las problemáticas que, según su observación, afectan la zona comercial donde se ubica su comercio:",
         "name": "problematicas_zona_comercial",
         "required": True,
         "opciones": [
             "Presencia de personas en situación de calle (personas que viven permanentemente en la vía pública)",
             "Actividades sexuales comerciales en el entorno",
             "Consumo de alcohol en vía pública",
             "Consumo de drogas",
             "Acumulación de basura / aguas negras / alcantarillado deficiente",
             "Falta o deficiencia de alumbrado público",
             "Lotes baldíos y edificaciones abandonadas",
             "Ventas informales (ambulantes)",
             "Sitios de reciclaje o compra de chatarra (chatarreras)",
             "Intentos de cobro ilegal o exigencias indebidas en la zona comercial",
             "Otro",
             "No se observan en el lugar comercial",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro problema:",
         "name": "problematicas_zona_comercial_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{problematicas_zona_comercial}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "13. En los casos en que se observa consumo de drogas en los alrededores del local comercial, indique dónde ocurre:",
         "name": "consumo_drogas_donde_comercio",
         "required": True,
         "opciones": [
             "Área pública (calle, aceras, alrededores del local)",
             "Área semipública (parques, lotes abandonados)",
             "No se observa consumo",
             "Otro",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro lugar:",
         "name": "consumo_drogas_donde_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{consumo_drogas_donde_comercio}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "14. Indique las principales deficiencias de infraestructura vial que afectan el entorno del local comercial:",
         "name": "infra_vial_deficiencias_comercio",
         "required": True,
         "opciones": ["Calles en mal estado", "Falta de señalización", "Falta o deterioro de aceras", "Otro"],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es esa otra deficiencia:",
         "name": "infra_vial_deficiencias_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{infra_vial_deficiencias_comercio}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "15. Según su conocimiento u observación, indique si ha identificado situaciones de inseguridad asociadas al transporte en los alrededores de su comercio:",
         "name": "inseguridad_transporte_comercio",
         "required": True,
         "opciones": [
             "Transporte informal o no autorizado (taxis piratas)",
             "Plataformas de transporte digital que se estacionan de forma indebida u obstruyen el paso",
             "Paradas de bus cercanas percibidas como inseguras",
             "Servicios de reparto o mensajería (motocicleta, bicimoto) asociados a situaciones de riesgo",
             "Otro tipo de situación relacionada con el transporte",
             "No se observan situaciones de inseguridad asociadas al transporte",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro tipo de situación relacionada con el transporte:",
         "name": "inseguridad_transporte_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{inseguridad_transporte_comercio}}, '{slugify_name('Otro tipo de situación relacionada con el transporte')}')"},

        {"tipo_ui": "Selección única",
         "label": "16. ¿Con qué frecuencia observa presencia policial en el entorno del local comercial?",
         "name": "frecuencia_presencia_policial_comercio",
         "required": True,
         "opciones": ["Todos los días", "Varias veces por semana", "Una vez por semana", "Casi nunca", "Nunca"],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        # ---------------- Delitos ----------------
        {"tipo_ui": "Selección múltiple",
         "label": "17. Selección múltiple de delitos:",
         "name": "delitos_comercio",
         "required": True,
         "opciones": [
             "Disturbios en vía pública (riñas o agresiones)",
             "Daños a la propiedad (viviendas, comercios, vehículos u otros bienes)",
             "Extorsión (amenazas o intimidación para exigir cobro de dinero u otros beneficios de manera ilegal a comercios)",
             "Hurto (sustracción de artículos mediante el descuido)",
             "Compra o venta de artículos robados (receptación)",
             "Contrabando (licor, cigarrillos, medicinas, ropa, calzado, etc.)",
             "Maltrato animal",
             "Otro",
             "No se observan delitos",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro delito:",
         "name": "delitos_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{delitos_comercio}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "18. Según su conocimiento u observación, ¿de qué forma se presenta la venta de drogas en los alrededores de local comercial?",
         "name": "venta_drogas_forma_comercio",
         "required": True,
         "opciones": [
             "En espacios cerrados (casas, edificaciones u otros inmuebles)",
             "En vía pública",
             "De forma ocasional o móvil modalidad exprés (sin punto fijo)",
             "No se observa venta de drogas",
             "Otro",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro modo de venta de drogas:",
         "name": "venta_drogas_forma_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{venta_drogas_forma_comercio}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "19. Asaltos:",
         "name": "asaltos_comercio",
         "required": True,
         "opciones": [
             "Asalto a personas",
             "Asalto a comercios",
             "Asalto en transporte público",
             "Otro",
             "No se observan asaltos",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro asalto:",
         "name": "asaltos_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{asaltos_comercio}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "20. Estafas que afectan al comercio",
         "name": "estafas_comercio",
         "required": True,
         "opciones": [
             "Billetes falsos",
             "Documentos falsos",
             "Estafas con oro",
             "Estafas con lotería",
             "Estafas informáticas",
             "Estafa telefónica",
             "Estafa con tarjetas",
             "Otro",
             "No se observan estafas",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es esa otra estafa:",
         "name": "estafas_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{estafas_comercio}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "21. Robos (Sustracción mediante la utilización de la fuerza)",
         "name": "robos_comercio",
         "required": True,
         "opciones": [
             "Robo a comercios",
             "Robo a edificaciones (bodegas, locales cerrados)",
             "Robo a viviendas cercanas al comercio",
             "Robo de vehículos completos",
             "Robo a vehículos (tacha o sustracción de partes)",
             "Robo de cable",
             "No se observan robos",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},
    ]

    st.session_state.preguntas = [ensure_qid(q) for q in seed]
    st.session_state.seed_cargado = True

# ✅ Asegurar qid también si ya existían preguntas en session_state (por ejemplo al recargar)
st.session_state.preguntas = [ensure_qid(q) for q in st.session_state.preguntas]
# ============================== PARTE 2 / 4 ==============================
# ------------------------------------------------------------------------------------------
# Sidebar: Metadatos + Exportar/Importar proyecto
# ------------------------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuración")
    form_title = st.text_input(
        "Título del formulario",
        value=(f"Encuesta comercio – {delegacion.strip()}" if delegacion.strip() else "Encuesta comercio"),
        key="sb_form_title"
    )
    idioma = st.selectbox("Idioma por defecto (default_language)", options=["es", "en"], index=0, key="sb_idioma")
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión (settings.version)", value=version_auto, key="sb_version")

    st.markdown("---")
    st.caption("💾 Exporta/Importa tu proyecto (JSON)")
    col_exp, col_imp = st.columns(2)

    if col_exp.button("Exportar proyecto (JSON)", use_container_width=True, key="btn_export_json"):
        proj = {
            "form_title": form_title,
            "idioma": idioma,
            "version": version,
            "preguntas": st.session_state.preguntas,  # incluye qid
            "reglas_visibilidad": st.session_state.reglas_visibilidad,
            "reglas_finalizar": st.session_state.reglas_finalizar,
            "choices_ext_rows": st.session_state.choices_ext_rows,
            "choices_extra_cols": list(st.session_state.choices_extra_cols),
            "textos_fijos": st.session_state.textos_fijos,
        }
        jbuf = BytesIO(json.dumps(proj, ensure_ascii=False, indent=2).encode("utf-8"))
        st.download_button(
            "Descargar JSON",
            data=jbuf,
            file_name="proyecto_encuesta_comercio.json",
            mime="application/json",
            use_container_width=True
        )

    up = col_imp.file_uploader("Importar JSON", type=["json"], label_visibility="collapsed", key="uploader_json")
    if up is not None:
        try:
            raw = up.read().decode("utf-8")
            data = json.loads(raw)

            preguntas = list(data.get("preguntas", []))
            st.session_state.preguntas = [ensure_qid(q) for q in preguntas]

            st.session_state.reglas_visibilidad = list(data.get("reglas_visibilidad", []))
            st.session_state.reglas_finalizar = list(data.get("reglas_finalizar", []))
            st.session_state.choices_ext_rows = list(data.get("choices_ext_rows", []))
            st.session_state.choices_extra_cols = set(data.get("choices_extra_cols", []))
            st.session_state.textos_fijos = dict(data.get("textos_fijos", st.session_state.textos_fijos))

            st.session_state.edit_qid = None
            _asegurar_placeholders_catalogo()
            _rerun()
        except Exception as e:
            st.error(f"No se pudo importar el JSON: {e}")

# ------------------------------------------------------------------------------------------
# Constructor: Agregar nuevas preguntas
# ------------------------------------------------------------------------------------------
st.subheader("📝 Diseña tus preguntas")

with st.form("form_add_q", clear_on_submit=False):
    tipo_ui = st.selectbox("Tipo de pregunta", options=TIPOS, key="add_tipo")
    label = st.text_input("Etiqueta (texto exacto)", key="add_label")
    sugerido = slugify_name(label) if label else ""
    col_n1, col_n2, col_n3 = st.columns([2, 1, 1])
    name = col_n1.text_input("Nombre interno (XLSForm 'name')", value=sugerido, key="add_name")
    required = col_n2.checkbox("Requerida", value=False, key="add_required")
    appearance = col_n3.text_input("Appearance (opcional)", value="", key="add_appearance")

    opciones = []
    if tipo_ui in ("Selección única", "Selección múltiple"):
        st.markdown("**Opciones (una por línea)**")
        txt_opts = st.text_area("Opciones", height=120, key="add_opts")
        if txt_opts.strip():
            opciones = [o.strip() for o in txt_opts.splitlines() if o.strip()]

    add = st.form_submit_button("➕ Agregar pregunta")

if add:
    if not label.strip():
        st.warning("Agrega una etiqueta.")
    else:
        base = slugify_name(name or label)
        usados = {q["name"] for q in st.session_state.preguntas}
        unico = asegurar_nombre_unico(base, usados)

        nueva = ensure_qid({
            "tipo_ui": tipo_ui,
            "label": label.strip(),
            "name": unico,
            "required": required,
            "opciones": opciones,
            "appearance": (appearance.strip() or None),
            "choice_filter": None,
            "relevant": None
        })
        st.session_state.preguntas.append(nueva)
        st.session_state.edit_qid = None
        st.success(f"Pregunta agregada: **{label}** (name: `{unico}`)")
        _rerun()

# ------------------------------------------------------------------------------------------
# Lista / Ordenado / Edición (completa) — editor por qid estable
# ------------------------------------------------------------------------------------------
st.subheader("📚 Preguntas (ordénalas y edítalas)")

if not st.session_state.preguntas:
    st.info("Aún no has agregado preguntas.")
else:
    for idx, q in enumerate(st.session_state.preguntas):
        q = ensure_qid(q)
        qid = q["qid"]

        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 2])

            c1.markdown(f"**{idx+1}. {q['label']}**")
            meta = f"type: {q['tipo_ui']}  •  name: `{q['name']}`  •  requerida: {'sí' if q['required'] else 'no'}"
            if q.get("appearance"):
                meta += f"  •  appearance: `{q['appearance']}`"
            if q.get("choice_filter"):
                meta += f"  •  choice_filter: `{q['choice_filter']}`"
            if q.get("relevant"):
                meta += f"  •  relevant: `{q['relevant']}`"
            if q.get("list_override"):
                meta += f"  •  list_override: `{q['list_override']}`"
            c1.caption(meta)

            if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                c1.caption("Opciones: " + ", ".join(q.get("opciones") or []))

            up_btn = c2.button("⬆️ Subir", key=f"up_{qid}", use_container_width=True, disabled=(idx == 0))
            down_btn = c3.button("⬇️ Bajar", key=f"down_{qid}", use_container_width=True, disabled=(idx == len(st.session_state.preguntas) - 1))
            edit_btn = c4.button("✏️ Editar", key=f"edit_{qid}", use_container_width=True)
            del_btn = c5.button("🗑️ Eliminar", key=f"del_{qid}", use_container_width=True)

            if up_btn:
                st.session_state.preguntas[idx - 1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx - 1]
                _rerun()

            if down_btn:
                st.session_state.preguntas[idx + 1], st.session_state.preguntas[idx] = st.session_state.preguntas[idx], st.session_state.preguntas[idx + 1]
                _rerun()

            if edit_btn:
                st.session_state.edit_qid = qid
                _rerun()

            if del_btn:
                if st.session_state.edit_qid == qid:
                    st.session_state.edit_qid = None
                del st.session_state.preguntas[idx]
                st.warning("Pregunta eliminada.")
                _rerun()

            if st.session_state.edit_qid == qid:
                st.markdown("**Editar esta pregunta**")

                ne_label = st.text_input("Etiqueta", value=q["label"], key=f"e_label_{qid}")
                ne_name = st.text_input("Nombre interno (name)", value=q["name"], key=f"e_name_{qid}")
                ne_required = st.checkbox("Requerida", value=q["required"], key=f"e_req_{qid}")
                ne_appearance = st.text_input("Appearance", value=q.get("appearance") or "", key=f"e_app_{qid}")
                ne_choice_filter = st.text_input("choice_filter (opcional)", value=q.get("choice_filter") or "", key=f"e_cf_{qid}")
                ne_relevant = st.text_input("relevant (opcional)", value=q.get("relevant") or "", key=f"e_rel_{qid}")

                ne_opciones = q.get("opciones") or []
                if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                    ne_opts_txt = st.text_area("Opciones (una por línea)", value="\n".join(ne_opciones), key=f"e_opts_{qid}")
                    ne_opciones = [o.strip() for o in ne_opts_txt.splitlines() if o.strip()]

                col_ok, col_cancel = st.columns(2)

                if col_ok.button("💾 Guardar cambios", key=f"e_save_{qid}", use_container_width=True):
                    cur_idx = q_index_by_qid(qid)
                    if cur_idx == -1:
                        st.error("No se encontró la pregunta (posible cambio de estado). Intenta de nuevo.")
                        st.session_state.edit_qid = None
                        _rerun()

                    new_base = slugify_name(ne_name or ne_label)
                    usados = {qq["name"] for j, qq in enumerate(st.session_state.preguntas) if j != cur_idx}
                    ne_name_final = new_base if new_base not in usados else asegurar_nombre_unico(new_base, usados)

                    st.session_state.preguntas[cur_idx]["label"] = ne_label.strip() or q["label"]
                    st.session_state.preguntas[cur_idx]["name"] = ne_name_final
                    st.session_state.preguntas[cur_idx]["required"] = ne_required
                    st.session_state.preguntas[cur_idx]["appearance"] = ne_appearance.strip() or None
                    st.session_state.preguntas[cur_idx]["choice_filter"] = ne_choice_filter.strip() or None
                    st.session_state.preguntas[cur_idx]["relevant"] = ne_relevant.strip() or None

                    if q["tipo_ui"] in ("Selección única", "Selección múltiple"):
                        st.session_state.preguntas[cur_idx]["opciones"] = ne_opciones

                    st.success("Cambios guardados.")
                    st.session_state.edit_qid = None
                    _rerun()

                if col_cancel.button("Cancelar", key=f"e_cancel_{qid}", use_container_width=True):
                    st.session_state.edit_qid = None
                    _rerun()

# ------------------------------------------------------------------------------------------
# Condicionales (panel)
# ------------------------------------------------------------------------------------------
st.subheader("🔀 Condicionales (mostrar / finalizar)")
if not st.session_state.preguntas:
    st.info("Agrega preguntas para definir condicionales.")
else:
    with st.expander("👁️ Mostrar pregunta si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}

        target = st.selectbox("Pregunta a mostrar (target)", options=names,
                              format_func=lambda n: f"{n} — {labels_by_name[n]}",
                              key="vis_target")
        src = st.selectbox("Depende de (source)", options=names,
                           format_func=lambda n: f"{n} — {labels_by_name[n]}",
                           key="vis_src")
        op = st.selectbox("Operador", options=["=", "selected"], key="vis_op")
        src_q = next((qq for qq in st.session_state.preguntas if qq["name"] == src), None)

        vals = []
        if src_q and src_q.get("opciones"):
            vals = st.multiselect("Valores (usa texto, internamente se usará slug)", options=src_q["opciones"], key="vis_vals")
            vals = [slugify_name(v) for v in vals]
        else:
            manual = st.text_input("Valor (si la pregunta no tiene opciones)", key="vis_manual")
            vals = [slugify_name(manual)] if manual.strip() else []

        if st.button("➕ Agregar regla de visibilidad", key="btn_add_vis"):
            if target == src:
                st.error("Target y Source no pueden ser la misma pregunta.")
            elif not vals:
                st.error("Indica al menos un valor.")
            else:
                st.session_state.reglas_visibilidad.append({"target": target, "src": src, "op": op, "values": vals})
                st.success("Regla agregada.")
                _rerun()

        if st.session_state.reglas_visibilidad:
            st.markdown("**Reglas de visibilidad actuales:**")
            for i, r in enumerate(st.session_state.reglas_visibilidad):
                st.write(f"- Mostrar **{r['target']}** si **{r['src']}** {r['op']} {r['values']}")
                if st.button(f"Eliminar regla #{i+1}", key=f"del_vis_{i}"):
                    del st.session_state.reglas_visibilidad[i]
                    _rerun()

    with st.expander("⏹️ Finalizar temprano si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}

        src2 = st.selectbox("Condición basada en", options=names,
                            format_func=lambda n: f"{n} — {labels_by_name[n]}",
                            key="final_src")
        op2 = st.selectbox("Operador", options=["=", "selected", "!="], key="final_op")
        src2_q = next((qq for qq in st.session_state.preguntas if qq["name"] == src2), None)

        vals2 = []
        if src2_q and src2_q.get("opciones"):
            vals2 = st.multiselect("Valores (slug interno)", options=src2_q["opciones"], key="final_vals")
            vals2 = [slugify_name(v) for v in vals2]
        else:
            manual2 = st.text_input("Valor (si no hay opciones)", key="final_manual")
            vals2 = [slugify_name(manual2)] if manual2.strip() else []

        if st.button("➕ Agregar regla de finalización", key="btn_add_fin"):
            if not vals2:
                st.error("Indica al menos un valor.")
            else:
                idx_src = next((i for i, qq in enumerate(st.session_state.preguntas) if qq["name"] == src2), 0)
                st.session_state.reglas_finalizar.append({"src": src2, "op": op2, "values": vals2, "index_src": idx_src})
                st.success("Regla agregada.")
                _rerun()

        if st.session_state.reglas_finalizar:
            st.markdown("**Reglas de finalización actuales:**")
            for i, r in enumerate(st.session_state.reglas_finalizar):
                st.write(f"- Si **{r['src']}** {r['op']} {r['values']} ⇒ ocultar lo que sigue (efecto fin)")
                if st.button(f"Eliminar regla fin #{i+1}", key=f"del_fin_{i}"):
                    del st.session_state.reglas_finalizar[i]
                    _rerun()
# ============================== PARTE 3 / 4 ==============================
# ------------------------------------------------------------------------------------------
# Construcción XLSForm (survey / choices / settings)
# ------------------------------------------------------------------------------------------
def _slug_opt(opt: str) -> str:
    return slugify_name(opt)

def _es_no_observa(opt: str) -> bool:
    o = (opt or "").strip().lower()
    return o.startswith("no se observa") or o.startswith("no se observan")

def _build_exclusive_constraint(qname: str, opciones: List[str]) -> Dict[str, str]:
    """
    Si existe una opción tipo "No se observa / No se observan ...", la vuelve EXCLUSIVA en select_multiple:
    - Si marca "No se observa...", no puede marcar ninguna otra.
    """
    no_opts = [o for o in opciones if _es_no_observa(o)]
    if not no_opts:
        return {"constraint": None, "constraint_message": None}

    no_slug = _slug_opt(no_opts[0])
    other_slugs = [_slug_opt(o) for o in opciones if _slug_opt(o) != no_slug]

    if not other_slugs:
        return {"constraint": None, "constraint_message": None}

    # not( selected(${q},'no') and (selected(${q},'a') or selected(${q},'b') ... ) )
    inner = " or ".join([f"selected(${{{qname}}}, '{s}')" for s in other_slugs])
    constraint = f"not(selected(${{{qname}}}, '{no_slug}') and ({inner}))"
    msg = "Si selecciona “No se observa / No se observan”, no seleccione otras opciones."
    return {"constraint": constraint, "constraint_message": msg}

def _apply_visibility_rules_to_questions(preguntas: List[Dict], reglas: List[Dict]) -> List[Dict]:
    """
    Aplica reglas (target depende de source) construyendo relevant y combinándolo con relevant existente.
    """
    # agrupar por target
    by_target = {}
    for r in reglas:
        by_target.setdefault(r["target"], []).append(r)

    out = []
    for q in preguntas:
        q2 = dict(q)
        rules = by_target.get(q2["name"], [])
        if rules:
            expr = build_relevant_expr(rules)
            if q2.get("relevant"):
                q2["relevant"] = f"({q2['relevant']}) and ({expr})"
            else:
                q2["relevant"] = expr
        out.append(q2)
    return out

def _apply_finish_rules_to_questions(preguntas: List[Dict], reglas_fin: List[Dict]) -> List[Dict]:
    """
    Finalizar temprano:
    - Para cada regla: si condición se cumple en src, ocultar todas las preguntas posteriores (relevant = not(cond)).
    """
    out = [dict(q) for q in preguntas]

    # ordenar reglas por index_src por si vienen desordenadas
    reglas_sorted = sorted(reglas_fin, key=lambda r: int(r.get("index_src", 0)))

    for r in reglas_sorted:
        src = r["src"]
        op = r.get("op", "=")
        vals = r.get("values", [])
        idx_src = int(r.get("index_src", 0))

        if not vals:
            continue

        if op == "=":
            parts = [f"${{{src}}}='{v}'" for v in vals]
        elif op == "selected":
            parts = [f"selected(${{{src}}}, '{v}')" for v in vals]
        elif op == "!=":
            parts = [f"${{{src}}}!='{v}'" for v in vals]
        else:
            parts = [f"${{{src}}}='{v}'" for v in vals]

        cond = xlsform_or_expr(parts)
        neg = xlsform_not(cond)

        for i in range(idx_src + 1, len(out)):
            # no tocar preguntas que ya están “fuera” por consentimiento (eso lo manejamos por páginas)
            if out[i].get("relevant"):
                out[i]["relevant"] = f"({out[i]['relevant']}) and ({neg})"
            else:
                out[i]["relevant"] = neg

    return out

def _make_settings_df(form_title: str, version: str, idioma: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "form_title": form_title,
        "form_id": slugify_name(form_title),
        "version": version,
        "default_language": idioma,
        "style": "pages",
    }])

def _build_choices(preguntas: List[Dict]) -> pd.DataFrame:
    """
    Construye hoja 'choices' de XLSForm.
    Incluye:
      - list_canton + list_distrito (de st.session_state.choices_ext_rows)
      - listas de cada select (list_{name}) o list_override
    """
    rows = []

    # 1) catálogo Cantón/Distrito (con columnas extra)
    cat_rows = _filtrar_placeholders_si_hay_catalogo(st.session_state.choices_ext_rows)
    for r in cat_rows:
        rows.append(dict(r))

    # 2) listas propias por pregunta
    used_keys = set((r.get("list_name"), r.get("name")) for r in rows)

    for q in preguntas:
        if q["tipo_ui"] not in ("Selección única", "Selección múltiple"):
            continue

        # canton/distrito usan catálogos, no generamos opciones aquí
        if q["name"] in ("canton", "distrito"):
            continue

        list_name = q.get("list_override") or f"list_{q['name']}"
        for opt in (q.get("opciones") or []):
            name = _slug_opt(opt)
            key = (list_name, name)
            if key in used_keys:
                continue
            used_keys.add(key)
            rows.append({"list_name": list_name, "name": name, "label": opt})

    if not rows:
        return pd.DataFrame(columns=["list_name", "name", "label"])

    # columns: base + extras
    cols = ["list_name", "name", "label"]
    extra = sorted(list(st.session_state.choices_extra_cols)) if st.session_state.choices_extra_cols else []
    cols = cols + [c for c in extra if c not in cols]

    df = pd.DataFrame(rows)
    # asegurar todas las columnas
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    return df

def _q_to_survey_row(q: Dict) -> Dict:
    """
    Convierte una pregunta del editor a una fila XLSForm 'survey'
    """
    tipo, appearance_default, list_name = map_tipo_to_xlsform(q["tipo_ui"], q["name"])

    # list_override (Matriz 9)
    if q.get("list_override") and q["tipo_ui"] in ("Selección única", "Selección múltiple"):
        if q["tipo_ui"] == "Selección única":
            tipo = f"select_one {q['list_override']}"
        else:
            tipo = f"select_multiple {q['list_override']}"

    appearance = q.get("appearance") or appearance_default

    row = {
        "type": tipo,
        "name": q["name"],
        "label": q["label"],
        "required": "yes" if q.get("required") else "",
        "relevant": q.get("relevant") or "",
        "appearance": appearance or "",
        "choice_filter": q.get("choice_filter") or "",
        "constraint": "",
        "constraint_message": "",
        "media::image": "",
    }

    # Exclusividad "No se observa..." solo para select_multiple
    if q["tipo_ui"] == "Selección múltiple":
        c = _build_exclusive_constraint(q["name"], q.get("opciones") or [])
        if c["constraint"]:
            row["constraint"] = c["constraint"]
            row["constraint_message"] = c["constraint_message"]

    return row

def _note_row(name: str, label: str, image: str = "", relevant: str = "") -> Dict:
    return {
        "type": "note",
        "name": name,
        "label": label,
        "required": "",
        "relevant": relevant or "",
        "appearance": "",
        "choice_filter": "",
        "constraint": "",
        "constraint_message": "",
        "media::image": image or "",
    }

def _begin_group(name: str, label: str, appearance: str = "", relevant: str = "") -> Dict:
    return {
        "type": "begin group",
        "name": name,
        "label": label,
        "required": "",
        "relevant": relevant or "",
        "appearance": appearance or "",
        "choice_filter": "",
        "constraint": "",
        "constraint_message": "",
        "media::image": "",
    }

def _end_group() -> Dict:
    return {
        "type": "end group",
        "name": "",
        "label": "",
        "required": "",
        "relevant": "",
        "appearance": "",
        "choice_filter": "",
        "constraint": "",
        "constraint_message": "",
        "media::image": "",
    }

def _build_survey(preguntas: List[Dict]) -> pd.DataFrame:
    """
    Construye hoja 'survey' con páginas reales:
      1) Intro (logo + INTRO_COMERCIO)
      2) Consentimiento (bloques + select_one)
      3) Datos Demográficos (intro comercio + canton/distrito/edad/género/escolaridad/tipo local + otro)
      4) II Percepción
      5) III Riesgos
      6) Delitos
      7) Final (si NO consiente)
    """
    # aplicar reglas del editor sobre copia
    preguntas2 = _apply_visibility_rules_to_questions(preguntas, st.session_state.reglas_visibilidad)
    preguntas2 = _apply_finish_rules_to_questions(preguntas2, st.session_state.reglas_finalizar)

    # index por name
    qmap = {q["name"]: q for q in preguntas2}

    # nombres por sección (limpio)
    demog_names = [
        "canton", "distrito", "edad_rango", "genero", "escolaridad",
        "tipo_local_comercial", "tipo_local_otro",
    ]
    percep_names = [
        "percep_seg_local", "motivos_inseguridad_local", "motivos_inseguridad_local_otro",
        "cambio_seguridad_12m_comercio", "motivo_cambio_12m_comercio",
        # Matriz 9: grupo especial (m9_*)
        "m9_afuera_comercio", "m9_pasillos_aceras", "m9_parqueos", "m9_paradas_bus", "m9_calles_cercanas",
        "foco_inseguridad_comercio", "foco_inseguridad_comercio_otro",
        "horarios_mayor_inseguridad",
    ]
    riesgos_names = [
        "problematicas_zona_comercial", "problematicas_zona_comercial_otro",
        "consumo_drogas_donde_comercio", "consumo_drogas_donde_otro",
        "infra_vial_deficiencias_comercio", "infra_vial_deficiencias_otro",
        "inseguridad_transporte_comercio", "inseguridad_transporte_otro",
        "frecuencia_presencia_policial_comercio",
    ]
    delitos_names = [
        "delitos_comercio", "delitos_comercio_otro",
        "venta_drogas_forma_comercio", "venta_drogas_forma_comercio_otro",
        "asaltos_comercio", "asaltos_comercio_otro",
        "estafas_comercio", "estafas_comercio_otro",
        "robos_comercio",
    ]

    # consentimiento
    consent_name = "consentimiento"
    consent_yes_slug = slugify_name("Sí")
    consent_no_slug = slugify_name("No")

    rows = []

    # ---------------- Página 1: Intro ----------------
    rows.append(_begin_group("page_intro", "Introducción"))
    rows.append(_note_row("intro_logo", "", image=logo_media_name))
    rows.append(_note_row("intro_texto", INTRO_COMERCIO))
    rows.append(_end_group())

    # ---------------- Página 2: Consentimiento ----------------
    rows.append(_begin_group("page_consent", "Consentimiento Informado"))
    rows.append(_note_row("cons_titulo", CONSENTIMIENTO_TITULO))
    for i, b in enumerate(CONSENTIMIENTO_BLOQUES, start=1):
        rows.append(_note_row(f"cons_bloque_{i}", b))
    if consent_name in qmap:
        rows.append(_q_to_survey_row(qmap[consent_name]))
    else:
        # por seguridad
        rows.append({
            "type": "select_one list_consent",
            "name": "consentimiento",
            "label": "¿Acepta participar en esta encuesta?",
            "required": "yes",
            "relevant": "",
            "appearance": "horizontal",
            "choice_filter": "",
            "constraint": "",
            "constraint_message": "",
            "media::image": "",
        })
    rows.append(_end_group())

    # ---------------- Página 3: Datos demográficos ----------------
    rows.append(_begin_group("page_demograficos", "I. Datos demográficos", relevant=f"${{{consent_name}}}='{consent_yes_slug}'"))
    rows.append(_note_row("demog_intro", INTRO_DEMOGRAFICOS_COMERCIO))
    for n in demog_names:
        if n in qmap:
            rows.append(_q_to_survey_row(qmap[n]))
    rows.append(_end_group())

    # ---------------- Página 4: II Percepción ----------------
    rows.append(_begin_group("page_percepcion", "II. Percepción ciudadana de seguridad en el comercio", relevant=f"${{{consent_name}}}='{consent_yes_slug}'"))
    rows.append(_note_row("percep_intro", INTRO_PERCEPCION_COMERCIO))

    # 7, 7.1, 8, 8.1
    for n in ["percep_seg_local", "motivos_inseguridad_local", "motivos_inseguridad_local_otro",
              "cambio_seguridad_12m_comercio", "motivo_cambio_12m_comercio"]:
        if n in qmap:
            rows.append(_q_to_survey_row(qmap[n]))

    # Matriz 9: begin group appearance=table-list
    rows.append(_begin_group("grp_matriz9", st.session_state.textos_fijos.get("matriz_9_label", ""), appearance="table-list",
                             relevant=f"${{{consent_name}}}='{consent_yes_slug}'"))
    # Nota dentro de matriz (como en imagen)
    rows.append(_note_row("m9_nota", "Nota: La persona encuestada podrá seleccionar una de las opciones por cada línea de zona."))
    for n in ["m9_afuera_comercio", "m9_pasillos_aceras", "m9_parqueos", "m9_paradas_bus", "m9_calles_cercanas"]:
        if n in qmap:
            rows.append(_q_to_survey_row(qmap[n]))
    rows.append(_end_group())

    # 10 y 11
    for n in ["foco_inseguridad_comercio", "foco_inseguridad_comercio_otro", "horarios_mayor_inseguridad"]:
        if n in qmap:
            rows.append(_q_to_survey_row(qmap[n]))

    rows.append(_end_group())

    # ---------------- Página 5: III Riesgos ----------------
    rows.append(_begin_group("page_riesgos", "III. Riesgos, delitos, victimización", relevant=f"${{{consent_name}}}='{consent_yes_slug}'"))
    rows.append(_note_row("riesgos_intro", INTRO_RIESGOS_COMERCIO))
    for n in riesgos_names:
        if n in qmap:
            rows.append(_q_to_survey_row(qmap[n]))
    rows.append(_end_group())

    # ---------------- Página 6: Delitos ----------------
    rows.append(_begin_group("page_delitos", "Delitos", relevant=f"${{{consent_name}}}='{consent_yes_slug}'"))
    rows.append(_note_row("delitos_intro", INTRO_DELITOS_COMERCIO))
    for n in delitos_names:
        if n in qmap:
            rows.append(_q_to_survey_row(qmap[n]))
    rows.append(_end_group())

    # ---------------- Página final: si NO consiente ----------------
    rows.append(_begin_group("page_final_no", "Finalizar", relevant=f"${{{consent_name}}}='{consent_no_slug}'"))
    rows.append(_note_row("fin_no",
                          "Gracias. Usted indicó que **NO** acepta participar. "
                          "La encuesta finaliza en este punto. Puede enviar el formulario.",
                          relevant=f"${{{consent_name}}}='{consent_no_slug}'"))
    rows.append(_end_group())

    df = pd.DataFrame(rows)

    # asegurar columnas mínimas típicas
    cols = ["type", "name", "label", "required", "relevant", "appearance", "choice_filter",
            "constraint", "constraint_message", "media::image"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    return df

def export_xlsform_bytes(form_title: str, version: str, idioma: str) -> bytes:
    """
    Genera XLSForm en memoria (bytes).
    """
    survey_df = _build_survey(st.session_state.preguntas)
    choices_df = _build_choices(st.session_state.preguntas)
    settings_df = _make_settings_df(form_title, version, idioma)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        survey_df.to_excel(writer, sheet_name="survey", index=False)
        choices_df.to_excel(writer, sheet_name="choices", index=False)
        settings_df.to_excel(writer, sheet_name="settings", index=False)

    return output.getvalue()

# ------------------------------------------------------------------------------------------
# Vista rápida (opcional) + Exportar XLSForm
# ------------------------------------------------------------------------------------------
st.subheader("📦 Exportar XLSForm (Survey123)")

col_prev, col_down = st.columns([2, 1], vertical_alignment="center")

with col_prev:
    if st.checkbox("Ver vista previa de hojas (survey/choices/settings)", value=False, key="chk_preview"):
        try:
            survey_preview = _build_survey(st.session_state.preguntas)
            choices_preview = _build_choices(st.session_state.preguntas)
            settings_preview = _make_settings_df(form_title, version, idioma)

            st.markdown("**survey**")
            st.dataframe(survey_preview, use_container_width=True, hide_index=True, height=260)

            st.markdown("**choices**")
            st.dataframe(choices_preview, use_container_width=True, hide_index=True, height=260)

            st.markdown("**settings**")
            st.dataframe(settings_preview, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Error en vista previa: {e}")

with col_down:
    st.caption("✅ El nombre del archivo usa el texto ACTUAL de “Nombre del lugar/Delegación”.")
    if st.button("🧾 Generar XLSForm", type="primary", use_container_width=True, key="btn_gen_xlsform"):
        try:
            st.session_state["_xlsform_bytes"] = export_xlsform_bytes(form_title, version, idioma)
            st.success("XLSForm generado. Usa el botón de descarga.")
        except Exception as e:
            st.error(f"No se pudo generar el XLSForm: {e}")

    if st.session_state.get("_xlsform_bytes"):
        st.download_button(
            "⬇️ Descargar XLSForm",
            data=st.session_state["_xlsform_bytes"],
            file_name=_nombre_archivo_xlsform(),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="btn_download_xlsform"
        )
# ============================== PARTE 4 / 4 ==============================
# ------------------------------------------------------------------------------------------
# Pequeñas mejoras UX + Avisos finales
# ------------------------------------------------------------------------------------------
st.markdown("---")
with st.expander("ℹ️ Notas importantes (Survey123 Connect)", expanded=False):
    st.markdown("""
- El XLSForm generado trae `settings.style = pages`, así que cada **grupo (begin/end group)** será una **página**.
- Para que la **portada muestre el logo**, copie el archivo de imagen dentro de la carpeta **media** del proyecto en Survey123 Connect,
  y asegúrese de que el nombre coincida con el valor en **Nombre de archivo para `media::image`**.
- El catálogo Cantón→Distrito se genera en **choices** usando `choice_filter = canton_key=${canton}`.
- En preguntas de selección múltiple, si existe una opción tipo **“No se observa / No se observan …”**:
  - se vuelve **exclusiva** (no permite marcar otras simultáneamente).
- La “Matriz 9” se exporta como un grupo `appearance = table-list` y todas las filas comparten el mismo `list_name`
  (por eso se ve como tabla).
""")

st.markdown("✅ Proyecto COMERCIO actualizado: Intro + Consentimiento + Demográficos + Percepción + Riesgos + Delitos.")


