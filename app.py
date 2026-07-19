"""
============================================================
 TELEGRAM POST PUBLISHER - Internal Streamlit App
============================================================
"""

import html
import io
import json
import base64
from datetime import date, datetime

import gspread
import requests
import streamlit as st
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# ------------------------------------------------------------------
# PAGE CONFIGURATION & CSS
# ------------------------------------------------------------------
modo_autenticado = st.session_state.get("is_authenticated", False)

st.set_page_config(page_title="Telegram Publisher", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    p, h1, h2, h3, h4, h5, h6, span, div, input, button, label {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    .stIconMaterial, .material-symbols-rounded {
        font-family: 'Material Symbols Rounded' !important;
    }

    [data-testid="stMain"] {
        background-color: #F4F6F8;
    }

    [data-testid="stMainBlockContainer"] {
        max-width: 760px;
        margin: 5rem auto 3rem auto; 
        background-color: #FFFFFF;
        border-radius: 18px;
        padding: 2.75rem 3rem 3rem 3rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06), 0 10px 30px rgba(15, 23, 42, 0.05);
        animation: fadeInUp 0.45s ease;
    }

    @keyframes fadeInUp {
        from { opacity: 0; transform: translateY(10px); }
        to   { opacity: 1; transform: translateY(0); }
    }

    .app-title {
        font-size: 1.9rem;
        font-weight: 700;
        color: #16232D;
        margin: 0 0 0.35rem 0;
    }
    .app-subtitle {
        color: #7C8A94;
        font-size: 0.95rem;
        margin-bottom: 2rem;
    }

    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-primaryFormSubmit"] {
        background-color: #00E676 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 10px;
        font-weight: 700;
        padding-top: 0.6rem;
        padding-bottom: 0.6rem;
        box-shadow: 0 4px 10px rgba(0, 230, 118, 0.35) !important;
        transition: all 0.2s ease;
    }
    [data-testid="stBaseButton-primary"]:hover,
    [data-testid="stBaseButton-primaryFormSubmit"]:hover {
        background-color: #00C853 !important;
        box-shadow: 0 6px 14px rgba(0, 230, 118, 0.45) !important;
        transform: translateY(-1px);
    }
    [data-testid="stBaseButton-primary"]:active,
    [data-testid="stBaseButton-primaryFormSubmit"]:active {
        transform: translateY(0);
    }

    [data-testid="stBaseButton-secondary"],
    [data-testid="stBaseButton-secondaryFormSubmit"] {
        background-color: #7EC8E3 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 10px;
        font-weight: 700;
        padding-top: 0.6rem;
        padding-bottom: 0.6rem;
        box-shadow: 0 2px 8px rgba(126, 200, 227, 0.35) !important;
        transition: all 0.2s ease;
    }
    [data-testid="stBaseButton-secondary"]:hover,
    [data-testid="stBaseButton-secondaryFormSubmit"]:hover {
        background-color: #5FB8DA !important;
        box-shadow: 0 4px 14px rgba(95, 184, 218, 0.45) !important;
        transform: translateY(-1px);
    }

    [data-testid="stTextInputRootElement"] {
        border-radius: 8px !important;
        transition: box-shadow 0.2s ease, border-color 0.2s ease;
    }
    [data-testid="stTextInputRootElement"]:focus-within {
        border-color: #7EC8E3 !important;
        box-shadow: 0 0 0 3px rgba(126, 200, 227, 0.22) !important;
    }

    [data-testid="InputInstructions"] {
        display: none !important;
    }

    div[data-testid="stTextInputRootElement"]:has(input[aria-label="Price"]) {
        position: relative;
    }
    div[data-testid="stTextInputRootElement"]:has(input[aria-label="Price"]) input {
        padding-right: 1.9rem !important;
    }
    div[data-testid="stTextInputRootElement"]:has(input[aria-label="Price"])::after {
        content: "$";
        position: absolute;
        right: 0.85rem;
        top: 50%;
        transform: translateY(-50%);
        font-size: 1rem;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        color: #5A6B75;
        font-weight: 600;
        pointer-events: none;
    }

    [data-testid="stFileUploaderDropzone"] {
        background-color: #FAFBFC;
        border: 2px dashed #CBD5DA;
        border-radius: 14px;
        padding: 1.75rem 1rem !important;
        transition: border-color 0.2s ease, background-color 0.2s ease;
    }
    [data-testid="stFileUploaderDropzone"]:hover {
        border-color: #7EC8E3;
        background-color: #F3FAFD;
    }
    [data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] {
        color: #7EC8E3 !important;
    }

    [data-testid="stAlertContainer"] {
        border-radius: 10px;
        animation: fadeInUp 0.3s ease;
    }

    .st-key-preview_panel {
        position: sticky;
        top: 6rem;
        align-self: flex-start;
    }

    .tg-panel-label {
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #7C8A94;
        font-weight: 600;
        margin-bottom: 0.75rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

_ancho_maximo = "1300px" if modo_autenticado else "760px"
st.markdown(
    f"""
    <style>
    [data-testid="stMainBlockContainer"] {{
        max-width: {_ancho_maximo} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

NOMBRE_PESTANA_USUARIOS = "Usuarios"
NOMBRE_PESTANA_PRESETS = "Productos_Guardados"
PLATAFORMAS = ["Select an option...", "USFans", "Hipobuy", "ACBuy", "Litbuy", "Mulebuy", "Hoobuy", "Vigorbuy"]
MAX_LINKS = 5


# ------------------------------------------------------------------
# GOOGLE CLOUD (SHEETS & DRIVE) CONNECTION
# ------------------------------------------------------------------
def obtener_servicio_sheets():
    alcances = ["https://www.googleapis.com/auth/spreadsheets"]
    credenciales_dict = dict(st.secrets["gcp_service_account"])
    credenciales = ServiceAccountCredentials.from_service_account_info(credenciales_dict, scopes=alcances)
    return gspread.authorize(credenciales)

def obtener_servicio_drive():
    credenciales = UserCredentials(
        token=None,
        refresh_token=st.secrets["gdrive"]["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=st.secrets["gdrive"]["client_id"],
        client_secret=st.secrets["gdrive"]["client_secret"],
    )
    return build("drive", "v3", credentials=credenciales)

def obtener_hojas():
    cliente_sheets = obtener_servicio_sheets()
    id_hoja = st.secrets["gsheets"]["sheet_id"]
    libro = cliente_sheets.open_by_key(id_hoja)
    return libro.worksheet(NOMBRE_PESTANA_USUARIOS), libro.worksheet(NOMBRE_PESTANA_PRESETS)

def obtener_mapa_columnas(hoja):
    encabezados = hoja.row_values(1)
    return {nombre.strip(): idx + 1 for idx, nombre in enumerate(encabezados)}

def obtener_presets(hoja_presets, clave):
    registros = hoja_presets.get_all_records()
    presets = []
    for i, fila in enumerate(registros):
        if str(fila.get("Clave_Usuario", "")).strip() == clave:
            presets.append({"fila": i + 2, "datos": fila})
    return presets

def guardar_preset_en_sheets(hoja_presets, clave, nombre, precio, links_json, id_carpeta, fila_existente=None):
    if fila_existente:
        hoja_presets.update(f"A{fila_existente}:E{fila_existente}", [[clave, nombre, precio, links_json, id_carpeta]])
    else:
        hoja_presets.append_row([clave, nombre, precio, links_json, id_carpeta])

def obtener_o_crear_carpeta(servicio, nombre, id_padre):
    if not id_padre:
        st.error("El ID de la carpeta raíz (folder_id) está vacío en los Secrets.")
        st.stop()

    nombre_escapado = nombre.replace("'", "\\'")
    query = f"name='{nombre_escapado}' and '{id_padre}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"

    try:
        resultados = servicio.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
        archivos = resultados.get("files", [])
        if archivos:
            return archivos[0].get("id")
        metadata = {"name": nombre, "mimeType": "application/vnd.google-apps.folder", "parents": [id_padre]}
        carpeta = servicio.files().create(body=metadata, fields="id").execute()
        return carpeta.get("id")
    except Exception as error:
        st.error(f"❌ ERROR DE DRIVE: {str(error)}")
        st.stop()

def borrar_archivo_o_carpeta(servicio, file_id):
    try:
        servicio.files().delete(fileId=file_id).execute()
    except Exception:
        pass

def subir_imagenes_a_drive(servicio, imagenes, id_carpeta):
    for img in imagenes:
        img.seek(0)
        media = MediaIoBaseUpload(img, mimetype=img.type, resumable=True)
        metadata = {"name": img.name, "parents": [id_carpeta]}
        servicio.files().create(body=metadata, media_body=media, fields="id").execute()

class ImagenEnMemoria(io.BytesIO):
    def __init__(self, content, name, mimetype):
        super().__init__(content)
        self.name = name
        self.type = mimetype

def descargar_imagenes_de_drive(servicio, id_carpeta):
    query = f"'{id_carpeta}' in parents and trashed=false"
    resultados = servicio.files().list(q=query, spaces="drive", fields="files(id, name, mimeType)").execute()
    archivos = resultados.get("files", [])

    imagenes_descargadas = []
    for arch in archivos:
        request = servicio.files().get_media(fileId=arch["id"])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        imagenes_descargadas.append(ImagenEnMemoria(fh.read(), arch["name"], arch["mimeType"]))
    return imagenes_descargadas

def obtener_imagenes_finales(servicio_drive, usando_preset, folder_id, imagenes_subidas):
    if usando_preset:
        with st.spinner("Downloading images from cloud..."):
            imagenes = descargar_imagenes_de_drive(servicio_drive, folder_id)
            if not imagenes:
                st.error("Error: The cloud folder is empty. Please clear the preset and re-upload the images manually.")
                st.stop()
            return imagenes
    return imagenes_subidas

def guardar_preset_completo(servicio_drive, hoja_presets, presets_usuario, usuario, clave, nombre_articulo, precio, links_recopilados, imagenes_finales):
    nombre_usuario = usuario.get("Nombre", "User")
    folder_raiz = st.secrets["gdrive"]["folder_id"]

    preset_existente = next(
        (p for p in presets_usuario if p["datos"]["Nombre_Articulo"].strip().lower() == nombre_articulo.strip().lower()),
        None,
    )
    user_folder_id = obtener_o_crear_carpeta(servicio_drive, nombre_usuario, folder_raiz)

    if preset_existente:
        old_folder_id = preset_existente["datos"].get("ID_Carpeta_Drive")
        if old_folder_id:
            borrar_archivo_o_carpeta(servicio_drive, old_folder_id)

    prod_folder_id = obtener_o_crear_carpeta(servicio_drive, nombre_articulo, user_folder_id)
    subir_imagenes_a_drive(servicio_drive, imagenes_finales, prod_folder_id)

    links_json = json.dumps(links_recopilados)
    guardar_preset_en_sheets(
        hoja_presets,
        clave.strip(),
        nombre_articulo,
        precio,
        links_json,
        prod_folder_id,
        fila_existente=preset_existente["fila"] if preset_existente else None,
    )

# ------------------------------------------------------------------
# TELEGRAM LOGIC
# ------------------------------------------------------------------
def construir_caption(nombre, precio, links_data):
    precio_str = str(precio).strip()
    if precio_str and not precio_str.endswith('$'):
        precio_str += '$'

    texto = "USFANS BEST FINDS💯\n\n"
    texto += f"🔎 Product: {html.escape(nombre)}\n"
    texto += f"💲 Price: {html.escape(precio_str)}\n\n"
    for plataforma, url in links_data:
        texto += f"🔗 <a href='{html.escape(url, quote=True)}'>{html.escape(plataforma)}</a>\n"
    return texto

def enviar_a_telegram(bot_token, chat_id, caption, imagenes):
    try:
        if len(imagenes) == 1:
            archivo = imagenes[0]
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            files = {"photo": (archivo.name, archivo.getvalue(), archivo.type)}
            data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
            respuesta = requests.post(url, data=data, files=files, timeout=30)
        else:
            url = f"https://api.telegram.org/bot{bot_token}/sendMediaGroup"
            media = []
            files = {}
            for i, archivo in enumerate(imagenes):
                clave_archivo = f"foto_{i}"
                item = {"type": "photo", "media": f"attach://{clave_archivo}"}
                if i == 0:
                    item["caption"] = caption
                    item["parse_mode"] = "HTML"
                media.append(item)
                files[clave_archivo] = (archivo.name, archivo.getvalue(), archivo.type)
            data = {"chat_id": chat_id, "media": json.dumps(media)}
            respuesta = requests.post(url, data=data, files=files, timeout=60)

        resultado = respuesta.json()
        if resultado.get("ok"):
            return True, ""
        return False, resultado.get("description", "Unknown Telegram Error")
    except requests.exceptions.RequestException as error:
        return False, f"Connection error with Telegram: {error}"

# ------------------------------------------------------------------
# LÍMITE DIARIO
# ------------------------------------------------------------------
def calcular_estado_uso(usuario):
    hoy = date.today()
    fecha_guardada = None
    if usuario.get("Ultima_Fecha"):
        for formato in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
            try:
                fecha_guardada = datetime.strptime(str(usuario.get("Ultima_Fecha")).strip(), formato).date()
                break
            except ValueError:
                pass
    usos_hoy_actual = int(usuario.get("Usos_Hoy") or 0)
    limite_diario = int(usuario.get("Límite_Diario") or usuario.get("Limite_Diario") or 0)
    usos_efectivos = 0 if fecha_guardada != hoy else usos_hoy_actual
    return usos_efectivos, limite_diario, hoy

def validar_campos_post(nombre, precio, links, imagenes):
    faltantes = []
    if not nombre:
        faltantes.append("Article Name")
    if not precio:
        faltantes.append("Price")
    if not links:
        faltantes.append("At least one link")
    if not imagenes:
        faltantes.append("At least one image")
    return faltantes

# ------------------------------------------------------------------
# CABECERA
# ------------------------------------------------------------------
st.markdown(
    """
    <div class="app-title">Telegram Post Publisher</div>
    <div class="app-subtitle">Created by Salty. Contact me at saltyreps@gmail.com</div>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# UI INITIALIZATION & SESSION STATE
# ------------------------------------------------------------------
if "ui_nombre" not in st.session_state:
    st.session_state.ui_nombre = ""
    st.session_state.ui_precio = ""
    for i in range(1, MAX_LINKS + 1):
        st.session_state[f"ui_plat_{i}"] = "Select an option..."
        st.session_state[f"ui_url_{i}"] = ""
    st.session_state.ui_folder_id = None
    st.session_state.num_visible_links = 2

# ------------------------------------------------------------------
# PANTALLA 1: ACCESO
# ------------------------------------------------------------------
if not modo_autenticado:
    st.markdown(
        "<h4 style='font-size: 1.05rem; color: #16232D; margin-bottom: 0.2rem;'>"
        "Please enter your access key provided by the owner.</h4>",
        unsafe_allow_html=True,
    )
    with st.form("auth_form", border=False):
        col_key, col_btn = st.columns([4, 1], vertical_alignment="bottom")
        with col_key:
            clave_input = st.text_input(
                "Access Key", type="password", placeholder="Enter your key", label_visibility="collapsed"
            )
        with col_btn:
            verify_pressed = st.form_submit_button("Verify", type="primary", use_container_width=True)

    if verify_pressed:
        clave_intentada = clave_input.strip()
        if not clave_intentada:
            st.warning("Please enter an access key.")
            st.stop()

        with st.spinner("Verifying access key & fetching database..."):
            try:
                hoja_auth, hoja_presets = obtener_hojas()
                col_map_auth = obtener_mapa_columnas(hoja_auth)

                registros = hoja_auth.get_all_records()
                fila_auth, usuario_auth = None, None
                for i, f in enumerate(registros):
                    if str(f.get("Clave", "")).strip() == clave_intentada:
                        fila_auth, usuario_auth = i + 2, f
                        break

                if usuario_auth is None:
                    st.error("Invalid access key. Please try again.")
                else:
                    st.session_state.is_authenticated = True
                    st.session_state.current_key = clave_intentada
                    st.session_state.user_data = usuario_auth
                    st.session_state.row_index = fila_auth
                    st.session_state.col_map = col_map_auth
                    st.session_state.user_presets = obtener_presets(hoja_presets, clave_intentada)

                    st.session_state.preset_selector = "Create New / Manual"
                    st.session_state.ui_nombre = ""
                    st.session_state.ui_precio = ""
                    for i in range(1, MAX_LINKS + 1):
                        st.session_state[f"ui_plat_{i}"] = "Select an option..."
                        st.session_state[f"ui_url_{i}"] = ""
                    st.session_state.ui_folder_id = None
                    st.session_state.num_visible_links = 2
                    st.rerun()
            except Exception as error:
                st.error(f"Could not connect to Google Cloud: {error}")

    st.stop()

# ------------------------------------------------------------------
# A partir de aquí, is_authenticated es garantizado True.
# ------------------------------------------------------------------
usuario = st.session_state.user_data
fila = st.session_state.row_index
col_map = st.session_state.col_map
presets_usuario = st.session_state.user_presets
clave = st.session_state.current_key

usos_efectivos_actual, limite_diario_actual, _ = calcular_estado_uso(usuario)
restantes_hoy = max(limite_diario_actual - usos_efectivos_actual, 0)
st.success(f"Access granted. Welcome, {usuario.get('Nombre', 'User')}! You have **{restantes_hoy}** post(s) left today.")
st.divider()

# ------------------------------------------------------------------
# MAIN FORM UI
# ------------------------------------------------------------------
nombres_presets = ["Create New / Manual"] + [p["datos"]["Nombre_Articulo"] for p in presets_usuario]

def apply_preset():
    opcion = st.session_state.preset_selector
    if opcion == "Create New / Manual":
        st.session_state.ui_nombre = ""
        st.session_state.ui_precio = ""
        for i in range(1, MAX_LINKS + 1):
            st.session_state[f"ui_plat_{i}"] = "Select an option..."
            st.session_state[f"ui_url_{i}"] = ""
        st.session_state.ui_folder_id = None
        st.session_state.num_visible_links = 2
    else:
        preset = next(p for p in presets_usuario if p["datos"]["Nombre_Articulo"] == opcion)
        st.session_state.ui_nombre = str(preset["datos"]["Nombre_Articulo"])
        st.session_state.ui_precio = str(preset["datos"]["Precio"])

        links_str = preset["datos"].get("Links", "[]")
        links_list = json.loads(links_str) if links_str else []

        for i in range(1, MAX_LINKS + 1):
            if i <= len(links_list):
                st.session_state[f"ui_plat_{i}"] = links_list[i - 1][0]
                st.session_state[f"ui_url_{i}"] = links_list[i - 1][1]
            else:
                st.session_state[f"ui_plat_{i}"] = "Select an option..."
                st.session_state[f"ui_url_{i}"] = ""
        st.session_state.ui_folder_id = preset["datos"].get("ID_Carpeta_Drive")
        st.session_state.num_visible_links = max(2, len(links_list))

col_preview, col_form = st.columns([1, 1.5], gap="large")

with col_form:
    st.subheader("Post Customization")

    st.selectbox("Saved Presets", nombres_presets, key="preset_selector", on_change=apply_preset)

    if st.session_state.ui_folder_id:
        st.success("✅ Images loaded automatically from your cloud storage.")
        imagenes_subidas = []
        usando_preset = True
    else:
        try:
            imagenes_subidas = st.file_uploader(
                "Product Images",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=True,
                max_upload_size=10, 
            )
        except TypeError:
            imagenes_subidas = st.file_uploader(
                "Product Images",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=True,
            )
        usando_preset = False

        if imagenes_subidas:
            archivos_grandes = [f.name for f in imagenes_subidas if f.size > 10 * 1024 * 1024]
            if archivos_grandes:
                st.error("These files exceed the 10MB limit: " + ", ".join(archivos_grandes))
                st.stop()

    nombre_articulo = st.text_input("Article Name", key="ui_nombre")
    precio = st.text_input("Price", placeholder="19.99", key="ui_precio")

    st.markdown("##### Links")
    links_recopilados = []

    for i in range(1, st.session_state.num_visible_links + 1):
        col1, col2 = st.columns([1, 2])
        with col1:
            plat_seleccionada = st.selectbox(f"Platform {i}", PLATAFORMAS, key=f"ui_plat_{i}")
        with col2:
            esta_bloqueado = plat_seleccionada == "Select an option..."
            link_url = st.text_input(f"URL {i}", disabled=esta_bloqueado, key=f"ui_url_{i}")

        if not esta_bloqueado and link_url.strip():
            links_recopilados.append((plat_seleccionada, link_url.strip()))

    if st.session_state.num_visible_links < MAX_LINKS:
        if st.button("➕ Add another link", type="tertiary"):
            st.session_state.num_visible_links += 1
            st.rerun()

    st.divider()

    col_send, col_save = st.columns([2, 1])
    with col_send:
        enviado = st.button("📨 Send to Telegram", use_container_width=True, type="secondary")
    with col_save:
        guardar_preset_btn = st.button("💾 Save as preset", use_container_width=True, type="primary")

    st.caption("Saving a preset does not publish anything and does not count against your daily limit.")

    if guardar_preset_btn:
        servicio_drive = obtener_servicio_drive()
        imagenes_finales = obtener_imagenes_finales(servicio_drive, usando_preset, st.session_state.ui_folder_id, imagenes_subidas)

        faltantes = validar_campos_post(nombre_articulo, precio, links_recopilados, imagenes_finales)
        if faltantes:
            st.warning("Missing fields to save the preset: " + ", ".join(faltantes))
            st.stop()

        with st.spinner("Saving preset to cloud..."):
            hoja_auth_p, hoja_presets_p = obtener_hojas()
            guardar_preset_completo(
                servicio_drive, hoja_presets_p, presets_usuario, usuario, clave,
                nombre_articulo, precio, links_recopilados, imagenes_finales,
            )
            st.session_state.user_presets = obtener_presets(hoja_presets_p, clave.strip())

        st.success(f"💾 Preset '{nombre_articulo}' saved. It did not count against your daily Telegram limit.")

    if enviado:
        servicio_drive = obtener_servicio_drive()
        imagenes_finales = obtener_imagenes_finales(servicio_drive, usando_preset, st.session_state.ui_folder_id, imagenes_subidas)

        faltantes = validar_campos_post(nombre_articulo, precio, links_recopilados, imagenes_finales)
        if faltantes:
            st.warning("Missing required fields: " + ", ".join(faltantes))
            st.stop()

        usos_efectivos, limite_diario, hoy = calcular_estado_uso(usuario)
        if usos_efectivos >= limite_diario:
            st.error(f"Daily limit reached ({limite_diario} posts). Please try again tomorrow.")
            st.stop()

        caption = construir_caption(nombre_articulo, precio, links_recopilados)

        with st.spinner("Publishing to Telegram..."):
            bot_token = st.secrets["telegram"]["bot_token"]
            channel_id = st.secrets["telegram"]["channel_id"]
            exito, error_msg = enviar_a_telegram(bot_token, channel_id, caption, imagenes_finales)

        if not exito:
            st.error(f"Error sending to Telegram: {error_msg}")
            st.stop()

        try:
            hoja_auth, _ = obtener_hojas()
            actualizaciones = [
                {"range": gspread.utils.rowcol_to_a1(fila, col_map["Usos_Hoy"]), "values": [[usos_efectivos + 1]]},
                {"range": gspread.utils.rowcol_to_a1(fila, col_map["Ultima_Fecha"]), "values": [[hoy.strftime("%Y-%m-%d")]]},
            ]
            hoja_auth.batch_update(actualizaciones)
        except Exception as error:
            st.warning(f"Published to Telegram, but could not update the limit counter in Sheets: {error}")
            st.stop()

        restantes = limite_diario - (usos_efectivos + 1)
        st.success(f"✅ Successfully published! You have {restantes} post(s) left today.")

# ------------------------------------------------------------------
# PREVIEW PANEL
# ------------------------------------------------------------------
with col_preview:
    with st.container(key="preview_panel"):
        st.markdown('<div class="tg-panel-label">📱 Telegram Preview</div>', unsafe_allow_html=True)

        # 1. Renderizar las imágenes de la burbuja (Base64)
        html_images = ""
        if usando_preset:
            html_images = '<div style="background-color: #E4E9EC; height: 120px; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 8px;"><span style="color: #8C9CA6; font-weight: 500; font-size: 0.85rem;">🖼️ Preset Images</span></div>'
        elif imagenes_subidas:
            imgs_b64 = []
            for img in imagenes_subidas[:3]:
                pos = img.tell()
                img.seek(0)
                imgs_b64.append(base64.b64encode(img.read()).decode())
                img.seek(pos)
            
            grid_class = "grid-1" if len(imgs_b64) == 1 else "grid-2" if len(imgs_b64) == 2 else "grid-3"
            html_images = f'<div class="telegram-images {grid_class}">'
            for b64 in imgs_b64:
                html_images += f'<img src="data:image/jpeg;base64,{b64}" />'
            html_images += '</div>'
            
            if len(imagenes_subidas) > 3:
                html_images += f'<div style="font-size: 0.75rem; color: #7C8A94; text-align: center; margin-bottom: 6px;">+{len(imagenes_subidas)-3} more image(s)</div>'

        # 2. Procesar el texto
        if nombre_articulo or precio or links_recopilados:
            caption_preview = construir_caption(nombre_articulo or "—", precio or "—", links_recopilados)
            caption_html = caption_preview.replace("\n", "<br>")
        else:
            caption_html = '<span style="color:#9AA7AE;">Fill in the form to see a preview…</span>'

        # 3. Construcción del entorno HTML/CSS Superpuesto usando URL web directa
        bg_style = "background-image: url('https://i.postimg.cc/59kbt8P9/Telegram-Chat-Builder-(Comunidad)-(1).png');"
        
        css_bloque = f"""
        <style>
        .iphone-preview {{
            position: relative;
            width: 100%;
            max-width: 360px; 
            aspect-ratio: 1712 / 3504;
            margin: 0 auto;
            {bg_style}
            background-size: cover;
            background-position: center;
            border-radius: 38px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.12), inset 0 0 0 6px #000;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            justify-content: flex-end; 
            padding: 0 7% 14% 7%; 
        }}
        .telegram-message {{
            background-color: #FFFFFF;
            border-radius: 16px 16px 16px 4px;
            padding: 4px;
            max-width: 90%;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            color: #000;
        }}
        .telegram-images {{
            display: grid;
            gap: 2px;
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 6px;
        }}
        .grid-1 {{ grid-template-columns: 1fr; }}
        .grid-2 {{ grid-template-columns: 1fr 1fr; grid-auto-rows: 150px; }}
        .grid-3 {{ grid-template-columns: 1fr 1fr; grid-template-rows: 80px 80px; }}
        .grid-3 img:first-child {{ grid-row: span 2; height: 100%; }}
        .telegram-images img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
        }}
        .telegram-text {{
            padding: 4px 8px 8px 8px;
            font-size: 0.88rem;
            line-height: 1.45;
        }}
        .telegram-text a {{
            color: #2481cc;
            text-decoration: none;
        }}
        </style>
        """

        # Inyectamos todo el HTML seguido en una sola línea para que sea imposible que falle el renderizado
        html_bloque = f'<div class="iphone-preview"><div class="telegram-message">{html_images}<div class="telegram-text">{caption_html}</div></div></div>'
        
        st.markdown(css_bloque + html_bloque, unsafe_allow_html=True)
