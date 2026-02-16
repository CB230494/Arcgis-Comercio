# ================================ PARTE 1 / 5 ============================================
# -*- coding: utf-8 -*-
# ==========================================================================================
# App: Encuesta COMERCIO → XLSForm para ArcGIS Survey123 (versión extendida)
# - Constructor completo (agregar/editar/ordenar/borrar)
# - Condicionales (relevant) + finalizar temprano
# - Listas en cascada (choice_filter) Cantón→Distrito [CATÁLOGO MANUAL POR LOTES]
# - Exportar/Importar proyecto (JSON)
# - Exportar a XLSForm (survey/choices/settings)
# - PÁGINAS reales (style="pages"): Intro + Consentimiento + P3.. (por secciones)
# - Portada con logo (media::image) y texto de introducción
# - Consentimiento:
#     - Texto en BLOQUES (notes separados) para que se vea ordenado en Survey123
#     - Si marca "No" ⇒ NO muestra el resto de páginas y cae a una página final para enviar
# - FIX: no mostrar placeholders “— escoja un cantón —” si hay catálogo real
# - FIX MATRIZ (table-list): todas las filas comparten el MISMO list_name (list_override)
# - FIX: Opciones "No se observa / No se observan ..." en select_multiple son EXCLUSIVAS
# - FIX: Al editar preguntas/opciones, los cambios SIEMPRE se reflejan (qid estable)
#
# ✅ ESTA VERSIÓN (5 PARTES) INCLUYE:
#   - P1 Intro Comercio 2026
#   - P2 Consentimiento + Finalización si NO
#   - P3 Datos demográficos + texto comercio + Q6 Tipo local comercial
#   - P4 II. Percepción Comercio (7–10 + Matriz 9)
#   - P5 III. Riesgos (11–16)
#   - P6 Delitos (17–21)
#   - P7 Victimización (22–23.1) (incluye 22.1 por bloques A–D)
#   - P8 Propuestas (24–25)
#   - P9 Confianza Policial (26–31)
#   - ✅ P10 Información Adicional y Contacto Voluntario (32–34)  ← NUEVO
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

# ✅ Textos fijos editables (Matriz 9 Comercio)
if "textos_fijos" not in st.session_state:
    st.session_state.textos_fijos = {
        "matriz_9_label_comercio": "9. En términos de seguridad, indique qué tan seguros percibe los siguientes espacios alrededor de su comercio."
    }

# Editor: solo una pregunta abierta a la vez (por qid estable)
if "edit_qid" not in st.session_state:
    st.session_state.edit_qid = None

with st.expander("✏️ Textos fijos (editables)", expanded=False):
    st.caption("Textos que NO son preguntas individuales (por ejemplo, encabezados internos como la Matriz 9).")
    st.session_state.textos_fijos["matriz_9_label_comercio"] = st.text_input(
        "Texto del encabezado de la Matriz 9 (Comercio)",
        value=st.session_state.textos_fijos.get("matriz_9_label_comercio", ""),
        key="txt_matriz9_comercio"
    )

# ------------------------------------------------------------------------------------------
# Catálogo manual por lotes: Cantón → Distritos
# ------------------------------------------------------------------------------------------
if "choices_ext_rows" not in st.session_state:
    st.session_state.choices_ext_rows = []
if "choices_extra_cols" not in st.session_state:
    st.session_state.choices_extra_cols = set()

def _append_choice_unique(row: Dict):
    key = (row.get("list_name"), row.get("name"))
    exists = any((r.get("list_name"), r.get("name")) == key for r in st.session_state.choices_ext_rows)
    if not exists:
        st.session_state.choices_ext_rows.append(row)

def _asegurar_placeholders_catalogo():
    """
    Survey123 exige list_canton/list_distrito en choices si se usan en survey.
    Garantiza placeholders aun cuando el usuario NO agregue lotes.
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
# Cabecera: Logo + Delegación
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

# ------------------------------------------------------------------------------------------
# Textos base (Intro / Consentimiento / Intros de páginas)
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

INTRO_DEMOG_COMERCIO = (
    "Con el fin de hacer más segura la zona comercial de este distrito, deseamos concentrarnos en los "
    "problemas de seguridad más importantes que afectan a los negocios. Queremos trabajar en conjunto con "
    "el gobierno local, otras instituciones y las personas comerciantes para reducir los delitos y riesgos "
    "que afectan la actividad comercial.\n\n"
    "Es importante recordarle que la información que usted nos proporcione es confidencial y se utilizará "
    "únicamente para mejorar la seguridad en esta zona comercial."
)

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

INTRO_PERCEPCION_COMERCIO = (
    "En esta sección le preguntaremos sobre cómo percibe la seguridad en el entorno donde desarrolla su actividad comercial. "
    "Las siguientes preguntas buscan conocer su opinión y experiencia sobre la seguridad en el lugar donde se ubica su negocio, "
    "así como en los espacios cercanos que forman parte de la dinámica comercial.\n\n"
    "Nos interesa saber cómo siente y cómo observa la seguridad en la zona comercial, cuáles situaciones generan mayor o menor tranquilidad "
    "y si considera que la situación ha mejorado, empeorado o se mantiene igual. Sus respuestas nos ayudarán a identificar qué factores generan "
    "preocupación en el comercio y cómo se vive la seguridad desde la actividad económica.\n\n"
    "Esta información se utilizará para apoyar el análisis preventivo del entorno comercial y orientar acciones de mejora y prevención. "
    "No hay respuestas correctas o incorrectas. Le pedimos responder con sinceridad, según su experiencia y percepción personal."
)

INTRO_RIESGOS_COMERCIO = (
    "A continuación, en esta sección le preguntaremos sobre situaciones o condiciones que pueden representar riesgos para la actividad comercial "
    "y la convivencia en la zona. Estas preguntas no se refieren necesariamente a delitos, sino a situaciones, comportamientos o problemáticas que "
    "usted haya observado y que puedan generar preocupación, afectar la operación del comercio o aumentar el riesgo de que ocurran hechos de inseguridad. "
    "Nos interesa conocer qué situaciones están presentes en el entorno comercial, con qué frecuencia se observan y en qué espacios se presentan, según su "
    "experiencia y percepción. Sus respuestas ayudarán a identificar factores de riesgo y a orientar acciones preventivas y de articulación local. "
    "No existen respuestas correctas o incorrectas. Le pedimos responder con sinceridad, de acuerdo con lo que ha visto o vivido en su entorno comercial."
)

INTRO_DELITOS_COMERCIO = (
    "A continuación, se presenta una lista de delitos para que indique aquellos que, según su conocimiento u observación, considera que se presentan "
    "en la zona donde desarrolla su actividad comercial. La información recopilada tiene fines de análisis preventivo y territorial y no constituye "
    "una denuncia formal ni la confirmación judicial de hechos delictivos."
)

INTRO_VICTIMIZACION_COMERCIO = (
    "A continuación, se presentará una lista de situaciones o hechos para que seleccione aquellos en los que su local comercial, o personas vinculadas "
    "a su actividad comercial, hayan sido directamente afectados en su zona comercial durante los últimos 12 meses. La información recopilada se utiliza "
    "con fines de análisis preventivo y no sustituye una denuncia formal."
)

INTRO_PROPUESTAS_COMERCIO = (
    "Las siguientes preguntas tienen como objetivo conocer la percepción ciudadana sobre acciones que podrían contribuir a la mejora de la seguridad desde "
    "el ámbito local e institucional. La información recolectada no constituye una evaluación de la gestión ni implica asignación de competencias o responsabilidades."
)

INTRO_CONFIANZA_POLICIAL = (
    "A continuación, se presentará una serie de preguntas relacionadas con su percepción y confianza en la Fuerza Pública que opera en el entorno del local comercial."
)

INTRO_INFO_ADICIONAL_CONTACTO = (
    "Esta sección final permite, de forma voluntaria, aportar información adicional que considere pertinente y, si lo desea, dejar un medio de contacto "
    "para continuar colaborando de manera confidencial con Fuerza Pública. La información suministrada será tratada con confidencialidad."
)

# ------------------------------------------------------------------------------------------
# Sidebar: Exportar/Importar proyecto (JSON) + Config
# ------------------------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuración")
    _ = st.text_input(
        "Título del formulario (referencia)",
        value=(f"Encuesta comercio – {delegacion.strip()}" if delegacion.strip() else "Encuesta comercio"),
        key="sb_form_title_ref"
    )
    idioma = st.selectbox("Idioma por defecto (default_language)", options=["es", "en"], index=0, key="sb_idioma")
    version_auto = datetime.now().strftime("%Y%m%d%H%M")
    version = st.text_input("Versión (settings.version)", value=version_auto, key="sb_version")

    st.markdown("---")
    st.caption("💾 Exporta/Importa tu proyecto (JSON)")
    col_exp, col_imp = st.columns(2)

    if col_exp.button("Exportar proyecto (JSON)", use_container_width=True, key="btn_export_json"):
        proj = {
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

# ============================ FIN PARTE 1 / 5 ============================================
# ================================ PARTE 2 / 5 ============================================
# (Continuación exacta)
# Aquí agregamos:
# ✅ Precarga (seed) COMPLETA de preguntas (hasta 34)
# ✅ Incluye la NUEVA última página: Información Adicional y Contacto Voluntario (32–34)
# ✅ Mantiene qid estable, slugify, y relevant correcto para “Otro” y para 32.1

# ------------------------------------------------------------------------------------------
# Precarga limpia de preguntas (seed) — COMERCIO (1..34)
# ------------------------------------------------------------------------------------------
if "seed_cargado" not in st.session_state:
    v_muy_inseguro = slugify_name("Muy inseguro")
    v_inseguro = slugify_name("Inseguro")

    SLUG_SI = slugify_name("Sí")
    SLUG_NO = slugify_name("No")

    # LISTA COMPARTIDA para matriz (table-list)
    LISTA_MATRIZ_COM = "list_matriz_comercio"

    seed = [
        # ---------------- Consentimiento ----------------
        {"tipo_ui": "Selección única",
         "label": "¿Acepta participar en esta encuesta?",
         "name": "consentimiento",
         "required": True,
         "opciones": ["Sí", "No"],
         "appearance": "horizontal",
         "choice_filter": None,
         "relevant": None},

        # ---------------- I. DATOS DEMOGRÁFICOS ----------------
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

        # ✅ 6 - Tipo de local comercial
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
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro tipo de local comercial:",
         "name": "tipo_local_comercial_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"${{tipo_local_comercial}}='{slugify_name('Otro')}'"},

        # ---------------- II. PERCEPCIÓN COMERCIO (7–10) ----------------
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
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "8.1. Indique por qué (explique brevemente la razón de su respuesta anterior):",
         "name": "motivo_cambio_12m_comercio",
         "required": True,
         "opciones": [],
         "appearance": "multiline",
         "choice_filter": None,
         "relevant": "string-length(${cambio_seguridad_12m_comercio})>0"},

        # 9 MATRIZ (table-list)
        {"tipo_ui": "Selección única", "label": "Afuera del comercio", "name": "seg_afuera_comercio",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_COM},

        {"tipo_ui": "Selección única", "label": "Pasillos / aceras comerciales", "name": "seg_pasillos_aceras",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_COM},

        {"tipo_ui": "Selección única", "label": "Parqueos", "name": "seg_parqueos",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_COM},

        {"tipo_ui": "Selección única", "label": "Paradas de bus", "name": "seg_paradas_bus",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_COM},

        {"tipo_ui": "Selección única", "label": "Calles cercanas", "name": "seg_calles_cercanas",
         "required": True,
         "opciones": ["Muy inseguro (1)", "Inseguro (2)", "Ni seguro ni inseguro (3)", "Seguro (4)", "Muy seguro (5)", "No aplica"],
         "appearance": None, "choice_filter": None, "relevant": None, "list_override": LISTA_MATRIZ_COM},

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
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro lugar:",
         "name": "foco_inseguridad_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"${{foco_inseguridad_comercio}}='{slugify_name('Otro (especifique)')}'"},

        # ---------------- III. RIESGOS (11–16) ----------------
        {"tipo_ui": "Selección múltiple",
         "label": "11. ¿En qué horarios percibe mayor inseguridad en el entorno comercial donde se ubica su comercio?",
         "name": "horarios_inseguridad_comercio",
         "required": True,
         "opciones": ["Mañana", "Tarde", "Noche", "Madrugada"],
         "appearance": None, "choice_filter": None, "relevant": None},

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
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro problema:",
         "name": "problematicas_zona_comercial_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{problematicas_zona_comercial}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "13. En los casos en que se observa consumo de drogas en los alrededores del local comercial, indique dónde ocurre (Marque todas las que observe):",
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
         "name": "consumo_drogas_donde_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{consumo_drogas_donde_comercio}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "14. Indique las principales deficiencias de infraestructura vial que afectan el entorno del local comercial:",
         "name": "infra_vial_deficiencias_comercio",
         "required": True,
         "opciones": [
             "Calles en mal estado",
             "Falta de señalización",
             "Falta o deterioro de aceras",
             "Otro",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es esa otra deficiencia:",
         "name": "infra_vial_deficiencias_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{infra_vial_deficiencias_comercio}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "15. Según su conocimiento u observación, indique si ha identificado situaciones de inseguridad asociadas al transporte en los alrededores de su comercio (Marque todas las que correspondan):",
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
         "name": "inseguridad_transporte_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{inseguridad_transporte_comercio}}, '{slugify_name('Otro tipo de situación relacionada con el transporte')}')"},

        {"tipo_ui": "Selección única",
         "label": "16. ¿Con qué frecuencia observa presencia policial en el entorno del local comercial?",
         "name": "frecuencia_presencia_policial_comercio",
         "required": True,
         "opciones": ["Todos los días", "Varias veces por semana", "Una vez por semana", "Casi nunca", "Nunca"],
         "appearance": None, "choice_filter": None, "relevant": None},

        # ===================== DELITOS (17–21) =====================
        {"tipo_ui": "Selección múltiple",
         "label": "17. Selección múltiple de delitos:",
         "name": "delitos_observados_zona",
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
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro delito:",
         "name": "delitos_observados_zona_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{delitos_observados_zona}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "18. Según su conocimiento u observación, ¿de qué forma se presenta la venta de drogas en los alrededores de local comercial?",
         "name": "venta_drogas_forma",
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
         "label": "Indique cuál es esa otra forma:",
         "name": "venta_drogas_forma_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{venta_drogas_forma}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "19. Asaltos:",
         "name": "asaltos_tipologia",
         "required": True,
         "opciones": [
             "Asalto a personas",
             "Asalto a comercios",
             "Asalto en transporte público",
             "Otro",
             "No se observan asaltos",
         ],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro tipo de asalto:",
         "name": "asaltos_tipologia_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{asaltos_tipologia}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "20. Estafas que afectan al comercio",
         "name": "estafas_tipologia",
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
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es esa otra estafa:",
         "name": "estafas_tipologia_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{estafas_tipologia}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "21. Robos (Sustracción mediante la utilización de la fuerza)",
         "name": "robos_tipologia",
         "required": True,
         "opciones": [
             "Robo a comercios",
             "Robo a edificaciones (bodegas, locales cerrados)",
             "Robo a viviendas cercanas al comercio",
             "Robo de vehículos completos",
             "Robo a vehículos (tacha o sustracción de partes)",
             "Robo de cable",
             "Otro",
             "No se observan robos",
         ],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro robo:",
         "name": "robos_tipologia_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{robos_tipologia}}, '{slugify_name('Otro')}')"},

        # ---------------- VICTIMIZACIÓN (22–23.1) ----------------
        {"tipo_ui": "Selección única",
         "label": "22. Durante los últimos 12 meses, ¿su local comercial fue afectado por algún delito?",
         "name": "victima_12m",
         "required": True,
         "opciones": ["No", "Sí, y denuncié", "Sí, pero no denuncié."],
         "appearance": None, "choice_filter": None, "relevant": None},

        # 22.1 por BLOQUES A/B/C/D (cada bloque es su select_multiple + Otro→texto)
        {"tipo_ui": "Selección múltiple",
         "label": "A. Robo y Asalto (Violencia y Fuerza)",
         "name": "victima_22_1_a",
         "required": True,
         "opciones": [
             "Asalto a mano armada (amenaza con arma o uso de violencia) en la calle o espacio público.",
             "Asalto en el transporte público (bus, taxi, metro, etc.).",
             "Asalto o robo de su vehículo (coche, motocicleta, etc.).",
             "Robo de accesorios o partes de su vehículo (espejos, llantas, radio).",
             "Robo o intento de robo con fuerza a su vivienda (ej. forzar una puerta o ventana).",
             "Robo o intento de robo con fuerza a su comercio o negocio.",
             "Otro",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro delito (Bloque A):",
         "name": "victima_22_1_a_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{victima_22_1_a}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "B. Hurto y Daños (Sin Violencia Directa)",
         "name": "victima_22_1_b",
         "required": True,
         "opciones": [
             "Hurto de su cartera, bolso o celular (sin que se diera cuenta, por descuido).",
             "Daños a su propiedad (ej. grafitis, rotura de cristales, destrucción de cercas).",
             "Compra o venta de artículos robados (receptación)",
             "Pérdida de artículos (celular, bicicleta, etc.) por descuido.",
             "Otro",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro delito (Bloque B):",
         "name": "victima_22_1_b_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{victima_22_1_b}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "C. Fraude y Engaño (Estafas)",
         "name": "victima_22_1_c",
         "required": True,
         "opciones": [
             "Estafa telefónica (ej. llamadas para pedir dinero o datos personales).",
             "Estafa o fraude informático (ej. a través de internet, redes sociales o correo electrónico).",
             "Fraude con tarjetas bancarias (clonación o uso no autorizado).",
             "Ser víctima de billetes o documentos falsos.",
             "Otro",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro delito (Bloque C):",
         "name": "victima_22_1_c_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{victima_22_1_c}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "D. Otros Delitos y Problemas Personales",
         "name": "victima_22_1_d",
         "required": True,
         "opciones": [
             "Extorsión (intimidación o amenaza para obtener dinero u otro beneficio).",
             "Maltrato animal (si usted o alguien de su hogar fue testigo o su mascota fue la víctima).",
             "Acoso o intimidación sexual en un espacio público.",
             "Algún tipo de delito sexual (abuso, violación).",
             "Lesiones personales (haber sido herido en una riña o agresión).",
             "Violencia Intrafamiliar (violencia domestica)",
             "Otro",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro delito (Bloque D):",
         "name": "victima_22_1_d_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{victima_22_1_d}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "22.2 En caso de NO haber realizado la denuncia ante el OIJ, indique cuál fue el motivo:",
         "name": "motivo_no_denuncia",
         "required": True,
         "opciones": [
             "Distancia o dificultad de acceso a oficinas para denunciar",
             "Miedo a represalias.",
             "Falta de respuesta o seguimiento en denuncias anteriores",
             "Complejidad o dificultad para realizar la denuncia (trámites, requisitos, tiempo)",
             "Desconocimiento de dónde colocar la denuncia (falta de información)",
             "El Policía me dijo que era mejor no denunciar.",
             "Falta de tiempo para colocar la denuncia",
             "Desconfianza en las autoridades o en el proceso de denuncia",
             "Otro",
         ],
         "appearance": None, "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro motivo:",
         "name": "motivo_no_denuncia_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{motivo_no_denuncia}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección única",
         "label": "22.3 ¿Tiene conocimiento del horario en el cual se presentó el hecho delictivo que afectó a su local comercial o a personas vinculadas a su actividad comercial?",
         "name": "horario_hecho_delictivo",
         "required": True,
         "opciones": [
             "00:00 – 02:59 (madrugada)",
             "03:00 – 05:59 (madrugada)",
             "06:00 – 08:59 (mañana)",
             "09:00 – 11:59 (mañana)",
             "12:00 – 14:59 (mediodía / tarde)",
             "15:00 – 17:59 (tarde)",
             "18:00 – 20:59 (noche)",
             "21:00 – 23:59 (noche)",
             "Desconocido",
         ],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Selección múltiple",
         "label": "23. ¿Cuál fue la forma o modo en que ocurrió la situación que afectó a su local comercial?",
         "name": "modo_ocurrio_hecho",
         "required": True,
         "opciones": [
             "Arma blanca (cuchillo, machete, tijeras).",
             "Arma de fuego.",
             "Amenazas",
             "Arrebato",
             "Boquete",
             "Ganzúa (pata de chancho)",
             "Engaño",
             "No sé.",
             "Otro",
         ],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro modo:",
         "name": "modo_ocurrio_hecho_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{modo_ocurrio_hecho}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "23.1 Incidentes de inseguridad asociados a la operación del comercio",
         "name": "incidentes_operacion_comercio",
         "required": True,
         "opciones": [
             "Riñas o disturbios dentro del local",
             "Riñas o disturbios en las inmediaciones del comercio",
             "Agresiones físicas al personal del comercio",
             "Amenazas verbales al personal",
             "Ingreso de personas en estado de ebriedad o bajo efectos de drogas que generaron conflictos",
             "Daños ocasionados por clientes o terceros",
             "Ninguno de los anteriores",
             "Otro",
         ],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es ese otro incidente:",
         "name": "incidentes_operacion_comercio_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{incidentes_operacion_comercio}}, '{slugify_name('Otro')}')"},

        # ---------------- PROPUESTAS (24–25) ----------------
        {"tipo_ui": "Selección múltiple",
         "label": "24. ¿Qué actividad considera que deba realizar la Fuerza Pública para mejorar la seguridad en zona comercial?",
         "name": "propuesta_fp",
         "required": True,
         "opciones": [
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
         ],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es esa otra actividad (Fuerza Pública):",
         "name": "propuesta_fp_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{propuesta_fp}}, '{slugify_name('Otro')}')"},

        {"tipo_ui": "Selección múltiple",
         "label": "25. ¿Qué actividad considera que deba realizar la municipalidad para mejorar la seguridad en zona comercial?",
         "name": "propuesta_muni",
         "required": True,
         "opciones": [
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
         ],
         "appearance": "columns", "choice_filter": None, "relevant": None},

        {"tipo_ui": "Texto (corto)",
         "label": "Indique cuál es esa otra actividad (Municipalidad):",
         "name": "propuesta_muni_otro",
         "required": True,
         "opciones": [],
         "appearance": None, "choice_filter": None,
         "relevant": f"selected(${{propuesta_muni}}, '{slugify_name('Otro')}')"},

        # ---------------- CONFIANZA POLICIAL (26–31) ----------------
        {"tipo_ui": "Selección única",
         "label": "26. ¿Cómo ha sido el servicio policial de Fuerza Pública de Costa Rica en los últimos 24 meses?",
         "name": "servicio_policial_24m",
         "required": True,
         "opciones": ["Mejor servicio", "Igual", "Peor servicio"],
         "appearance": "horizontal",
         "choice_filter": None,
         "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "27. ¿Conoce usted a los policías de la Fuerza Pública de Costa Rica de su zona comercial?",
         "name": "conoce_policias_zona",
         "required": True,
         "opciones": ["Sí", "No"],
         "appearance": "horizontal",
         "choice_filter": None,
         "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "28. ¿Conoce el programa de \"Seguridad Comercial\" que imparte Fuerza Pública?",
         "name": "conoce_programa_seg_com",
         "required": True,
         "opciones": ["Sí", "No"],
         "appearance": "horizontal",
         "choice_filter": None,
         "relevant": None},

        {"tipo_ui": "Selección única",
         "label": "29. ¿Está inscrito en el programa de \"Seguridad Comercial\" que imparte Fuerza Pública?",
         "name": "inscrito_programa_seg_com",
         "required": True,
         "opciones": ["Sí", "No"],
         "appearance": "horizontal",
         "choice_filter": None,
         "relevant": f"${{conoce_programa_seg_com}}='{SLUG_SI}'"},

        {"tipo_ui": "Selección única",
         "label": "30. ¿Le gustaría que se le contacte para formar parte del programa?",
         "name": "quiere_contacto_programa",
         "required": True,
         "opciones": ["Sí", "No"],
         "appearance": "horizontal",
         "choice_filter": None,
         "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "31. Si su respuesta es afirmativa, indicar nombre del comercio, correo electrónico y número de teléfono para contactarlo(a)",
         "name": "datos_contacto_programa",
         "required": True,
         "opciones": [],
         "appearance": "multiline",
         "choice_filter": None,
         "relevant": f"${{quiere_contacto_programa}}='{SLUG_SI}'"},

        # ===================== INFORMACIÓN ADICIONAL Y CONTACTO VOLUNTARIO (32–34) =====================
        {"tipo_ui": "Selección única",
         "label": "32. ¿Usted tiene información de alguna persona o grupo que se dedique a realizar algún delito en su comercio?",
         "name": "info_persona_grupo_delito",
         "required": True,
         "opciones": ["Sí", "No"],
         "appearance": "horizontal",
         "choice_filter": None,
         "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "32.1. Si su respuesta es \"SI\", describa aquellas características que pueda aportar tales como nombre de estructura o banda criminal... (nombre de personas, alias, domicilio, vehículos, etc.)",
         "name": "info_persona_grupo_delito_detalle",
         "required": True,
         "opciones": [],
         "appearance": "multiline",
         "choice_filter": None,
         "relevant": f"${{info_persona_grupo_delito}}='{SLUG_SI}'"},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "33. En el siguiente espacio de forma voluntaria podrá anotar su nombre, teléfono o correo electrónico en el cual desee ser contactado y continuar colaborando de forma confidencial con Fuerza Pública.",
         "name": "contacto_voluntario",
         "required": False,
         "opciones": [],
         "appearance": "multiline",
         "choice_filter": None,
         "relevant": None},

        {"tipo_ui": "Párrafo (texto largo)",
         "label": "34. En el siguiente espacio podrá registrar alguna otra información que estime pertinente.",
         "name": "info_adicional",
         "required": False,
         "opciones": [],
         "appearance": "multiline",
         "choice_filter": None,
         "relevant": None},
    ]

    st.session_state.preguntas = [ensure_qid(q) for q in seed]
    st.session_state.seed_cargado = True

# Asegurar qid también si ya existían preguntas en session_state
st.session_state.preguntas = [ensure_qid(q) for q in st.session_state.preguntas]

# ============================ FIN PARTE 2 / 5 ============================================
# ================================ PARTE 3 / 5 ============================================
# (Continuación exacta)
# Aquí va:
# ✅ Constructor: agregar preguntas
# ✅ Lista/ordenado/edición por qid estable
# ✅ Panel de condicionales (mostrar / finalizar)
# ==========================================================================================

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
    # Mostrar
    with st.expander("👁️ Mostrar pregunta si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}

        target = st.selectbox(
            "Pregunta a mostrar (target)",
            options=names,
            format_func=lambda n: f"{n} — {labels_by_name[n]}",
            key="vis_target"
        )
        src = st.selectbox(
            "Depende de (source)",
            options=names,
            format_func=lambda n: f"{n} — {labels_by_name[n]}",
            key="vis_src"
        )
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

    # Finalizar
    with st.expander("⏹️ Finalizar temprano si se cumple condición", expanded=False):
        names = [q["name"] for q in st.session_state.preguntas]
        labels_by_name = {q["name"]: q["label"] for q in st.session_state.preguntas}

        src2 = st.selectbox(
            "Condición basada en",
            options=names,
            format_func=lambda n: f"{n} — {labels_by_name[n]}",
            key="final_src"
        )
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

# ============================ FIN PARTE 3 / 5 ============================================
# ================================ PARTE 4 / 5 ============================================
# (Continuación exacta)
# Aquí SOLO va la función `construir_xlsform()` actualizada para:
# ✅ Mantener TODAS las páginas existentes
# ✅ Mantener la lógica de Victimización (22) exactamente como ya estaba
# ✅ Agregar la ÚLTIMA PÁGINA:
#    "Información Adicional y Contacto Voluntario" con preguntas 32–34 (y 32.1 con relevant)
# ==========================================================================================

def construir_xlsform(preguntas, form_title: str, idioma: str, version: str,
                      reglas_vis, reglas_fin):
    survey_rows = []
    choices_rows = []
    choices_keys = set()

    def _choices_add_unique(row: Dict):
        key = (row.get("list_name"), row.get("name"))
        if key not in choices_keys:
            choices_rows.append(row)
            choices_keys.add(key)

    idx_by_name = {q.get("name"): i for i, q in enumerate(preguntas)}

    vis_by_target = {}
    for r in reglas_vis:
        vis_by_target.setdefault(r["target"], []).append(
            {"src": r["src"], "op": r.get("op", "="), "values": r.get("values", [])}
        )

    fin_conds = []
    for r in reglas_fin:
        cond = build_relevant_expr([{"src": r["src"], "op": r.get("op", "="), "values": r.get("values", [])}])
        if cond:
            fin_conds.append((r["index_src"], cond))

    def _aplicar_exclusividad_no_observa(row: Dict, q: Dict):
        if q.get("tipo_ui") != "Selección múltiple":
            return
        opts = q.get("opciones") or []
        if not opts:
            return

        exclusivas = [o for o in opts if str(o).strip().lower().startswith("no se observa")]
        if not exclusivas:
            exclusivas = [o for o in opts if str(o).strip().lower().startswith("no se observan")]
        if not exclusivas:
            return

        ex_label = exclusivas[0]
        ex_slug = slugify_name(ex_label)
        nm = q["name"]

        row["constraint"] = f"not(selected(${{{nm}}}, '{ex_slug}') and count-selected(${{{nm}}})>1)"
        row["constraint_message"] = f"Si selecciona “{ex_label}”, no puede marcar otras opciones."

    def add_q(q, idx):
        x_type, default_app, list_name = map_tipo_to_xlsform(q["tipo_ui"], q["name"])

        # Matriz: list_override compartido
        list_override = q.get("list_override")
        if list_override and isinstance(x_type, str):
            if x_type.startswith("select_one "):
                x_type = f"select_one {list_override}"
                list_name = list_override
            elif x_type.startswith("select_multiple "):
                x_type = f"select_multiple {list_override}"
                list_name = list_override

        rel_manual = q.get("relevant") or None
        rel_panel = build_relevant_expr(vis_by_target.get(q["name"], []))

        nots = [xlsform_not(cond) for idx_src, cond in fin_conds if idx_src < idx]
        rel_fin = "(" + " and ".join(nots) + ")" if nots else None

        parts = [p for p in [rel_manual, rel_panel, rel_fin] if p]
        rel_final = parts[0] if parts and len(parts) == 1 else ("(" + ") and (".join(parts) + ")" if parts else None)

        row = {"type": x_type, "name": q["name"], "label": q["label"]}
        if q.get("required"):
            row["required"] = "yes"
        app = q.get("appearance") or default_app
        if app:
            row["appearance"] = app
        if q.get("choice_filter"):
            row["choice_filter"] = q["choice_filter"]
        if rel_final:
            row["relevant"] = rel_final

        # Constraints placeholders SOLO si NO hay catálogo real
        if not _hay_catalogo_real():
            if q["name"] == "canton":
                row["constraint"] = ". != '__pick_canton__'"
                row["constraint_message"] = "Seleccione un cantón válido."
            if q["name"] == "distrito":
                row["constraint"] = ". != '__pick_distrito__'"
                row["constraint_message"] = "Seleccione un distrito válido."

        # Exclusividad "No se observa / No se observan"
        _aplicar_exclusividad_no_observa(row, q)

        survey_rows.append(row)

        # Choices (excepto Cantón/Distrito)
        if list_name and q["name"] not in {"canton", "distrito"}:
            usados = set()
            for opt_label in (q.get("opciones") or []):
                base = slugify_name(opt_label)
                opt_name = asegurar_nombre_unico(base, usados)
                usados.add(opt_name)
                _choices_add_unique({"list_name": list_name, "name": opt_name, "label": str(opt_label)})

    # --------------------------------------------------------------------------------------
    # Página 1: Intro
    # --------------------------------------------------------------------------------------
    survey_rows += [
        {"type": "begin_group", "name": "p1_intro", "label": "Introducción", "appearance": "field-list"},
        {"type": "note", "name": "intro_logo", "label": form_title, "media::image": _get_logo_media_name()},
        {"type": "note", "name": "intro_texto", "label": INTRO_COMERCIO},
        {"type": "end_group", "name": "p1_end"},
    ]

    # --------------------------------------------------------------------------------------
    # Página 2: Consentimiento
    # --------------------------------------------------------------------------------------
    idx_consent = idx_by_name.get("consentimiento", None)
    survey_rows.append({"type": "begin_group", "name": "p2_consentimiento", "label": "Consentimiento informado", "appearance": "field-list"})
    survey_rows.append({"type": "note", "name": "cons_title", "label": CONSENTIMIENTO_TITULO})
    for i, txt in enumerate(CONSENTIMIENTO_BLOQUES, start=1):
        survey_rows.append({"type": "note", "name": f"cons_b{i:02d}", "label": txt})
    if idx_consent is not None:
        add_q(preguntas[idx_consent], idx_consent)
    survey_rows.append({"type": "end_group", "name": "p2_consentimiento_end"})

    # Página final si NO acepta
    survey_rows.append({
        "type": "begin_group",
        "name": "p_fin_no",
        "label": "Finalización",
        "appearance": "field-list",
        "relevant": f"${{consentimiento}}='{CONSENT_NO}'"
    })
    survey_rows.append({
        "type": "note",
        "name": "fin_no_texto",
        "label": "Gracias. Al no aceptar participar, la encuesta finaliza en este punto."
    })
    survey_rows.append({"type": "end_group", "name": "p_fin_no_end"})

    # Desde aquí, todo SOLO si consentimiento = Sí
    rel_si = f"${{consentimiento}}='{CONSENT_SI}'"

    # --------------------------------------------------------------------------------------
    # Sets por página
    # --------------------------------------------------------------------------------------
    p_demograficos = {
        "canton", "distrito", "edad_rango", "genero", "escolaridad",
        "tipo_local_comercial", "tipo_local_comercial_otro"
    }

    p_percepcion = {
        "percep_seg_local",
        "motivos_inseguridad_local",
        "motivos_inseguridad_local_otro",
        "cambio_seguridad_12m_comercio",
        "motivo_cambio_12m_comercio",
        "seg_afuera_comercio",
        "seg_pasillos_aceras",
        "seg_parqueos",
        "seg_paradas_bus",
        "seg_calles_cercanas",
        "foco_inseguridad_comercio",
        "foco_inseguridad_comercio_otro",
    }

    p_riesgos = {
        "horarios_inseguridad_comercio",
        "problematicas_zona_comercial",
        "problematicas_zona_comercial_otro",
        "consumo_drogas_donde_comercio",
        "consumo_drogas_donde_comercio_otro",
        "infra_vial_deficiencias_comercio",
        "infra_vial_deficiencias_comercio_otro",
        "inseguridad_transporte_comercio",
        "inseguridad_transporte_comercio_otro",
        "frecuencia_presencia_policial_comercio",
    }

    p_delitos = {
        "delitos_observados_zona",
        "delitos_observados_zona_otro",
        "venta_drogas_forma",
        "venta_drogas_forma_otro",
        "asaltos_tipologia",
        "asaltos_tipologia_otro",
        "estafas_tipologia",
        "estafas_tipologia_otro",
        "robos_tipologia",
        "robos_tipologia_otro",
    }

    p_victimizacion = {
        "victima_12m",
        "victima_22_1_a", "victima_22_1_a_otro",
        "victima_22_1_b", "victima_22_1_b_otro",
        "victima_22_1_c", "victima_22_1_c_otro",
        "victima_22_1_d", "victima_22_1_d_otro",
        "motivo_no_denuncia", "motivo_no_denuncia_otro",
        "horario_hecho_delictivo",
        "modo_ocurrio_hecho", "modo_ocurrio_hecho_otro",
        "incidentes_operacion_comercio", "incidentes_operacion_comercio_otro",
    }

    p_propuestas = {
        "propuesta_fp", "propuesta_fp_otro",
        "propuesta_muni", "propuesta_muni_otro",
    }

    p_confianza = {
        "servicio_policial_24m",
        "conoce_policias_zona",
        "conoce_programa_seg_com",
        "inscrito_programa_seg_com",
        "quiere_contacto_programa",
        "datos_contacto_programa",
    }

    # ✅ NUEVA ÚLTIMA PÁGINA
    p_info_adicional = {
        "info_persona_grupo_delito",
        "info_persona_grupo_delito_detalle",
        "contacto_voluntario",
        "info_adicional",
    }

    # --------------------------------------------------------------------------------------
    # Helper de páginas
    # --------------------------------------------------------------------------------------
    def add_page(group_name, page_label, names_set, intro_note_text: str = None,
                 group_appearance: str = "field-list", group_relevant: str = None,
                 extra_notes: List[Dict] = None):
        row = {"type": "begin_group", "name": group_name, "label": page_label, "appearance": group_appearance}
        if group_relevant:
            row["relevant"] = group_relevant
        survey_rows.append(row)

        if intro_note_text:
            note = {"type": "note", "name": f"{group_name}_intro", "label": intro_note_text}
            if group_relevant:
                note["relevant"] = group_relevant
            survey_rows.append(note)

        if extra_notes:
            for nn in extra_notes:
                nrow = dict(nn)
                if group_relevant and "relevant" not in nrow:
                    nrow["relevant"] = group_relevant
                survey_rows.append(nrow)

        for i, qq in enumerate(preguntas):
            if qq["name"] in names_set:
                add_q(qq, i)

        survey_rows.append({"type": "end_group", "name": f"{group_name}_end"})

    # --------------------------------------------------------------------------------------
    # P3 Demográficos
    # --------------------------------------------------------------------------------------
    add_page(
        "p3_demograficos",
        "I. DATOS DEMOGRÁFICOS",
        p_demograficos,
        intro_note_text=INTRO_DEMOG_COMERCIO,
        group_appearance="field-list",
        group_relevant=rel_si
    )

    # P4 Percepción
    add_page(
        "p4_percepcion_comercio",
        "II. PERCEPCIÓN CIUDADANA DE SEGURIDAD EN EL COMERCIO",
        p_percepcion,
        intro_note_text=INTRO_PERCEPCION_COMERCIO,
        group_appearance="field-list",
        group_relevant=rel_si
    )

    # P5 Riesgos
    add_page(
        "p5_riesgos_comercio",
        "III. RIESGOS, DELITOS, VICTIMIZACIÓN",
        p_riesgos,
        intro_note_text=INTRO_RIESGOS_COMERCIO,
        group_appearance="field-list",
        group_relevant=rel_si
    )

    # P6 Delitos
    add_page(
        "p6_delitos_comercio",
        "Delitos",
        p_delitos,
        intro_note_text=INTRO_DELITOS_COMERCIO,
        group_appearance="field-list",
        group_relevant=rel_si
    )

    # --------------------------------------------------------------------------------------
    # P7 Victimización (con 22.1 en BLOQUES y lógica)
    # --------------------------------------------------------------------------------------
    v_no = slugify_name("No")
    v_si_den = slugify_name("Sí, y denuncié")
    v_si_no_den = slugify_name("Sí, pero no denuncié.")

    rel_victima_denuncio = f"${{victima_12m}}='{v_si_den}'"
    rel_victima_no_denuncio = f"${{victima_12m}}='{v_si_no_den}'"
    rel_victima_si_cualquiera = xlsform_or_expr([rel_victima_denuncio, rel_victima_no_denuncio])

    rel_221 = rel_victima_si_cualquiera
    rel_222 = rel_victima_no_denuncio
    rel_223 = rel_victima_si_cualquiera
    rel_23 = rel_victima_si_cualquiera
    rel_231 = rel_victima_si_cualquiera

    note_221 = {
        "type": "note",
        "name": "victima_22_1_titulo",
        "label": "22.1 ¿Cuál fue el delito por el cual su local comercial o personas vinculadas a su actividad comercial resultaron directamente afectadas?",
        "relevant": rel_221
    }

    add_page(
        "p7_victimizacion_comercio",
        "Victimización",
        p_victimizacion,
        intro_note_text=INTRO_VICTIMIZACION_COMERCIO,
        group_appearance="field-list",
        group_relevant=rel_si,
        extra_notes=[note_221]
    )

    def _set_relevant_force(qname: str, expr: str):
        for qq in preguntas:
            if qq.get("name") == qname:
                qq["relevant"] = expr
                return

    _set_relevant_force("victima_22_1_a", rel_221)
    _set_relevant_force("victima_22_1_a_otro", f"{rel_221} and selected(${{victima_22_1_a}}, '{slugify_name('Otro')}')")

    _set_relevant_force("victima_22_1_b", rel_221)
    _set_relevant_force("victima_22_1_b_otro", f"{rel_221} and selected(${{victima_22_1_b}}, '{slugify_name('Otro')}')")

    _set_relevant_force("victima_22_1_c", rel_221)
    _set_relevant_force("victima_22_1_c_otro", f"{rel_221} and selected(${{victima_22_1_c}}, '{slugify_name('Otro')}')")

    _set_relevant_force("victima_22_1_d", rel_221)
    _set_relevant_force("victima_22_1_d_otro", f"{rel_221} and selected(${{victima_22_1_d}}, '{slugify_name('Otro')}')")

    _set_relevant_force("motivo_no_denuncia", rel_222)
    _set_relevant_force("motivo_no_denuncia_otro", f"{rel_222} and selected(${{motivo_no_denuncia}}, '{slugify_name('Otro')}')")

    _set_relevant_force("horario_hecho_delictivo", rel_223)

    _set_relevant_force("modo_ocurrio_hecho", rel_23)
    _set_relevant_force("modo_ocurrio_hecho_otro", f"{rel_23} and selected(${{modo_ocurrio_hecho}}, '{slugify_name('Otro')}')")

    _set_relevant_force("incidentes_operacion_comercio", rel_231)
    _set_relevant_force("incidentes_operacion_comercio_otro", f"{rel_231} and selected(${{incidentes_operacion_comercio}}, '{slugify_name('Otro')}')")

    # P8 Propuestas
    add_page(
        "p8_propuestas_comercio",
        "Propuestas ciudadanas para la mejora de la seguridad",
        p_propuestas,
        intro_note_text=INTRO_PROPUESTAS_COMERCIO,
        group_appearance="field-list",
        group_relevant=rel_si
    )

    # P9 Confianza Policial
    add_page(
        "p9_confianza_policial",
        "Confianza Policial",
        p_confianza,
        intro_note_text=INTRO_CONFIANZA_POLICIAL_COMERCIO,
        group_appearance="field-list",
        group_relevant=rel_si
    )

    # ✅ P10 Información Adicional y Contacto Voluntario
    add_page(
        "p10_info_adicional_contacto",
        "Información Adicional y Contacto Voluntario",
        p_info_adicional,
        intro_note_text=None,
        group_appearance="field-list",
        group_relevant=rel_si
    )

    # --------------------------------------------------------------------------------------
    # Encapsular matriz 9 en table-list
    # --------------------------------------------------------------------------------------
    def _postprocesar_matriz_table_list(df_survey: pd.DataFrame) -> pd.DataFrame:
        matriz_names = [
            "seg_afuera_comercio",
            "seg_pasillos_aceras",
            "seg_parqueos",
            "seg_paradas_bus",
            "seg_calles_cercanas",
        ]
        idxs = df_survey.index[df_survey["name"].isin(matriz_names)].tolist()
        if not idxs:
            return df_survey

        start = min(idxs)
        end = max(idxs)

        matriz_label = st.session_state.textos_fijos.get(
            "matriz_9_label_comercio",
            "9. En términos de seguridad, indique qué tan seguros percibe los siguientes espacios alrededor de su comercio."
        )

        begin_row = {
            "type": "begin_group",
            "name": "matriz_seguridad_9_comercio",
            "label": matriz_label,
            "appearance": "table-list",
        }
        end_row = {"type": "end_group", "name": "matriz_seguridad_9_comercio_end"}

        top = df_survey.iloc[:start].copy()
        mid = df_survey.iloc[start:end + 1].copy()
        bot = df_survey.iloc[end + 1:].copy()

        return pd.concat([top, pd.DataFrame([begin_row]), mid, pd.DataFrame([end_row]), bot], ignore_index=True)

    # --------------------------------------------------------------------------------------
    # Choices del catálogo Cantón/Distrito
    # --------------------------------------------------------------------------------------
    _asegurar_placeholders_catalogo()
    catalog_rows = [dict(r) for r in st.session_state.choices_ext_rows]
    catalog_rows = _filtrar_placeholders_si_hay_catalogo(catalog_rows)
    for r in catalog_rows:
        _choices_add_unique(r)

    # --------------------------------------------------------------------------------------
    # DataFrames
    # --------------------------------------------------------------------------------------
    survey_cols_all = set().union(*[r.keys() for r in survey_rows])
    survey_cols = [c for c in [
        "type", "name", "label", "required", "appearance", "choice_filter",
        "relevant", "constraint", "constraint_message", "media::image"
    ] if c in survey_cols_all]
    for k in sorted(survey_cols_all):
        if k not in survey_cols:
            survey_cols.append(k)

    df_survey = pd.DataFrame(survey_rows, columns=survey_cols)
    df_survey = _postprocesar_matriz_table_list(df_survey)

    choices_cols_all = set()
    for r in choices_rows:
        choices_cols_all.update(r.keys())
    base_choice_cols = ["list_name", "name", "label"]
    for extra in sorted(choices_cols_all):
        if extra not in base_choice_cols:
            base_choice_cols.append(extra)
    df_choices = pd.DataFrame(choices_rows, columns=base_choice_cols) if choices_rows else pd.DataFrame(columns=base_choice_cols)

    df_settings = pd.DataFrame([{
        "form_title": form_title,
        "version": version,
        "default_language": idioma,
        "style": "pages",
    }], columns=["form_title", "version", "default_language", "style"])

    return df_survey, df_choices, df_settings

# ============================ FIN PARTE 4 / 5 ============================================
# ================================ PARTE 5 / 5 ============================================
# ✅ CONTINUACIÓN EXACTA de tu código (NO CAMBIO nada de lo ya hecho).
# Esta parte agrega ÚNICAMENTE lo que falta para que TODO funcione:
# 1) Helper faltante: _get_logo_media_name()
# 2) ✅ Asegurar que existan las preguntas 32–34 (y 32.1) en el SEED si aún no están
# 3) Exportar XLSForm (survey/choices/settings) a Excel + botón de descarga
# 4) Previsualización (dataframes) antes de exportar
# ==========================================================================================

# ------------------------------------------------------------------------------------------
# Helper faltante para el logo en XLSForm
# ------------------------------------------------------------------------------------------
def _get_logo_media_name():
    """
    Devuelve el nombre del archivo que se usará en la columna media::image del XLSForm.
    Debe existir en la carpeta media/ del proyecto Survey123 (Survey123 Connect).
    """
    try:
        return st.session_state.get("_logo_name") or st.session_state.get("logo_media_txt") or "001.png"
    except Exception:
        return "001.png"

# ------------------------------------------------------------------------------------------
# ✅ Asegurar SEED de la ÚLTIMA PÁGINA: Información Adicional y Contacto Voluntario (32–34)
# (No rompe nada: solo agrega si NO existe)
# ------------------------------------------------------------------------------------------
def _add_if_missing_final(q: Dict):
    nm = q.get("name")
    if not nm:
        return
    exists = any(qq.get("name") == nm for qq in st.session_state.preguntas)
    if not exists:
        st.session_state.preguntas.append(ensure_qid(q))

if "seed_info_adicional_v1" not in st.session_state:
    SLUG_SI = slugify_name("Sí")
    SLUG_NO = slugify_name("No")

    # 32
    _add_if_missing_final({
        "tipo_ui": "Selección única",
        "label": "32. ¿Usted tiene información de alguna persona o grupo que se dedique a realizar algún delito en su comercio? (Recuerde, su información es confidencial.)",
        "name": "info_persona_grupo_delito",
        "required": True,
        "opciones": ["Sí", "No"],
        "appearance": "horizontal",
        "choice_filter": None,
        "relevant": None
    })

    # 32.1 (solo si 32 = Sí)
    _add_if_missing_final({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "32.1. Si su respuesta es \"SI\", describa aquellas características que pueda aportar tales como nombre de estructura o banda criminal... (nombre de personas, alias, domicilio, vehículos, etc.)",
        "name": "info_persona_grupo_delito_detalle",
        "required": True,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": f"${{info_persona_grupo_delito}}='{SLUG_SI}'"
    })

    # 33
    _add_if_missing_final({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "33. En el siguiente espacio de forma voluntaria podrá anotar su nombre, teléfono o correo electrónico en el cual desee ser contactado y continuar colaborando de forma confidencial con Fuerza Pública.",
        "name": "contacto_voluntario",
        "required": False,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": None
    })

    # 34
    _add_if_missing_final({
        "tipo_ui": "Párrafo (texto largo)",
        "label": "34. En el siguiente espacio podrá registrar alguna otra información que estime pertinente.",
        "name": "info_adicional",
        "required": False,
        "opciones": [],
        "appearance": "multiline",
        "choice_filter": None,
        "relevant": None
    })

    st.session_state.seed_info_adicional_v1 = True

# Asegurar qid en todo
st.session_state.preguntas = [ensure_qid(q) for q in st.session_state.preguntas]

# ------------------------------------------------------------------------------------------
# Exportar a XLSForm (Excel) + Vista previa
# ------------------------------------------------------------------------------------------
st.markdown("---")
st.subheader("📤 Exportar XLSForm (Survey123)")

# Construir dataframes
df_survey, df_choices, df_settings = construir_xlsform(
    preguntas=st.session_state.preguntas,
    form_title=titulo_compuesto,
    idioma=idioma,
    version=version,
    reglas_vis=st.session_state.reglas_visibilidad,
    reglas_fin=st.session_state.reglas_finalizar
)

# Vista previa
with st.expander("👀 Vista previa (survey / choices / settings)", expanded=False):
    st.caption("Estas son las hojas que se exportarán al XLSForm.")
    st.markdown("**survey**")
    st.dataframe(df_survey, use_container_width=True, hide_index=True, height=260)
    st.markdown("**choices**")
    st.dataframe(df_choices, use_container_width=True, hide_index=True, height=260)
    st.markdown("**settings**")
    st.dataframe(df_settings, use_container_width=True, hide_index=True, height=120)

# Generar Excel en memoria
def _to_excel_bytes(df_survey: pd.DataFrame, df_choices: pd.DataFrame, df_settings: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_survey.to_excel(writer, sheet_name="survey", index=False)
        df_choices.to_excel(writer, sheet_name="choices", index=False)
        df_settings.to_excel(writer, sheet_name="settings", index=False)
    output.seek(0)
    return output.getvalue()

xls_bytes = _to_excel_bytes(df_survey, df_choices, df_settings)

# Nombre de archivo sugerido
safe_deleg = slugify_name(delegacion or "comercio")
file_name = f"xlsform_encuesta_comercio_{safe_deleg}.xlsx"

st.download_button(
    "⬇️ Descargar XLSForm (Excel)",
    data=xls_bytes,
    file_name=file_name,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True
)

st.info(
    "📌 Recordatorio Survey123: coloca el archivo del logo (por ejemplo, "
    f"**{_get_logo_media_name()}**) dentro de la carpeta **media/** del proyecto en Survey123 Connect."
)

# ============================ FIN PARTE 5 / 5 ============================================
