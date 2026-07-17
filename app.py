"""
============================================================
 TELEGRAM POST PUBLISHER - Internal Streamlit App
============================================================
"""

import html
import io
import json
from datetime import date, datetime

import gspread
import requests
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# ------------------------------------------------------------------
# PAGE CONFIGURATION & CSS
# ------------------------------------------------------------------
st.set_page_config(page_title="Telegram Publisher", layout="centered")

st.markdown("""
    <style>
    [data-testid="baseButton-main"] {
        background-color: #ADD8E6 !important;
        color: #000000 !important;
        border: 1px solid #ADD8E6 !important;
        box-shadow: none !important;
        font-weight: 500 !important;
        transition: all 0.3s ease;
    }
    [data-testid="baseButton-main"]:hover {
        background-color: #87CEEB !important;
    }
    [data-testid="stFileUploadDropzone"] {
        padding: 4rem !important;
        background-color: #F8F9FA !important;
        border: 2px dashed #CCCCCC !important;
    }
    </style>
""", unsafe_allow_html=True)

NOMBRE_PESTANA_USUARIOS = "Usuarios"
NOMBRE_PESTANA_PRESETS = "Productos_Guardados"

# ------------------------------------------------------------------
# GOOGLE CLOUD (SHEETS & DRIVE) CONNECTION
# ------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def obtener_servicios_gcp():
    alcances = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credenciales_dict = dict(st.secrets["gcp_service_account"])
    credenciales = Credentials.from_service_account_info(credenciales_dict, scopes=alcances)
    
    cliente_sheets = gspread.authorize(credenciales)
    servicio_drive = build('drive', 'v3', credentials=credenciales)
    return cliente_sheets, servicio_drive

def obtener_hojas():
    cliente_sheets, _ = obtener_servicios_gcp()
    id_hoja = st.secrets["gsheets"]["sheet_id"]
    libro = cliente_sheets.open_by_key(id_hoja)
    return libro.worksheet(NOMBRE_PESTANA_USUARIOS), libro.worksheet(NOMBRE_PESTANA_PRESETS)

def obtener_mapa_columnas(hoja):
    encabezados = hoja.row_values(1)
    return {nombre.strip(): idx + 1 for idx, nombre in enumerate(encabezados)}

# --- LOGICA DE PRESETS EN SHEETS ---
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

# --- LOGICA DE GOOGLE DRIVE ---
def obtener_o_crear_carpeta(servicio, nombre, id_padre):
    # Comprobación de seguridad por si el ID de la carpeta principal está vacío
    if not id_padre:
        raise Exception("El ID de la carpeta raíz (folder_id) está vacío en los Secrets.")

    # Escapamos comillas simples para que no rompan la búsqueda interna de Drive
    nombre_escapado = nombre.replace("'", "\\'")
    query = f"name='{nombre_escapado}' and '{id_padre}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    
    try:
        resultados = servicio.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        archivos = resultados.get('files', [])
        if archivos:
            return archivos[0].get('id')
        else:
            metadata = {'name': nombre, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [id_padre]}
            carpeta = servicio.files().create(body=metadata, fields='id').execute()
            return carpeta.get('id')
    except Exception as error:
        # Esto atrapará el error real de Google y lo forzará en pantalla, saltándose la censura de Streamlit
        raise Exception(f"Error detallado de Google Drive: {error}. Query intentada: {query}")

def borrar_archivo_o_carpeta(servicio, file_id):
    try:
        servicio.files().delete(fileId=file_id).execute()
    except Exception:
        pass

def subir_imagenes_a_drive(servicio, imagenes, id_carpeta):
    for img in imagenes:
        img.seek(0)
        media = MediaIoBaseUpload(img, mimetype=img.type, resumable=True)
        metadata = {'name': img.name, 'parents': [id_carpeta]}
        servicio.files().create(body=metadata, media_body=media, fields='id').execute()

class ImagenEnMemoria(io.BytesIO):
    def __init__(self, content, name, mimetype):
        super().__init__(content)
        self.name = name
        self.type = mimetype

def descargar_imagenes_de_drive(servicio, id_carpeta):
    query = f"'{id_carpeta}' in parents and trashed=false"
    resultados = servicio.files().list(q=query, spaces='drive', fields='files(id, name, mimeType)').execute()
    archivos = resultados.get('files', [])
    
    imagenes_descargadas = []
    for arch in archivos:
        request = servicio.files().get_media(fileId=arch['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        imagenes_descargadas.append(ImagenEnMemoria(fh.read(), arch['name'], arch['mimeType']))
    return imagenes_descargadas


# ------------------------------------------------------------------
# TELEGRAM LOGIC
# ------------------------------------------------------------------
def construir_caption(nombre, precio, links_data):
    texto = f"<b>{html.escape(nombre)}</b>\n\n"
    texto += f"<b>Price:</b> {html.escape(precio)}\n\n"
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
# UI INITIALIZATION & SESSION STATE
# ------------------------------------------------------------------
# Initialize form values in memory
if "ui_nombre" not in st.session_state:
    st.session_state.ui_nombre = ""
    st.session_state.ui_precio = ""
    for i in range(1, 6):
        st.session_state[f"ui_plat_{i}"] = "Select an option..."
        st.session_state[f"ui_url_{i}"] = ""
    st.session_state.ui_folder_id = None

# 1. Pre-requisite authentication
clave = st.text_input("Access Key", type="password", placeholder="Enter your key and press Enter")

if not clave:
    st.stop()

# Auth & Data Fetching
if "current_key" not in st.session_state or st.session_state.current_key != clave:
    with st.spinner("Verifying access key & fetching database..."):
        try:
            hoja_auth, hoja_presets = obtener_hojas()
            col_map_auth = obtener_mapa_columnas(hoja_auth)
            
            # Buscamos el usuario
            registros = hoja_auth.get_all_records()
            fila_auth, usuario_auth = None, None
            for i, f in enumerate(registros):
                if str(f.get("Clave", "")).strip() == clave.strip():
                    fila_auth, usuario_auth = i + 2, f
                    break
            
            st.session_state.current_key = clave
            if usuario_auth is None:
                st.session_state.is_authenticated = False
            else:
                st.session_state.is_authenticated = True
                st.session_state.user_data = usuario_auth
                st.session_state.row_index = fila_auth
                st.session_state.col_map = col_map_auth
                st.session_state.user_presets = obtener_presets(hoja_presets, clave.strip())
                
                # Reseteamos la UI al hacer login nuevo
                st.session_state.preset_selector = "Create New / Manual"
                st.session_state.ui_nombre = ""
                st.session_state.ui_precio = ""
                for i in range(1, 6):
                    st.session_state[f"ui_plat_{i}"] = "Select an option..."
                    st.session_state[f"ui_url_{i}"] = ""
                st.session_state.ui_folder_id = None
                
        except Exception as error:
            st.error(f"Could not connect to Google Cloud: {error}")
            st.stop()

if not st.session_state.get("is_authenticated"):
    st.error("Invalid access key. Please try again.")
    st.stop()

usuario = st.session_state.user_data
fila = st.session_state.row_index
col_map = st.session_state.col_map
presets_usuario = st.session_state.user_presets

st.success(f"Access granted. Welcome, {usuario.get('Nombre', 'User')}!")
st.divider()

# ------------------------------------------------------------------
# MAIN FORM UI
# ------------------------------------------------------------------
st.subheader("Post Customization")

# --- PRESET SELECTOR ---
nombres_presets = ["Create New / Manual"] + [p["datos"]["Nombre_Articulo"] for p in presets_usuario]

def apply_preset():
    opcion = st.session_state.preset_selector
    if opcion == "Create New / Manual":
        st.session_state.ui_nombre = ""
        st.session_state.ui_precio = ""
        for i in range(1, 6):
            st.session_state[f"ui_plat_{i}"] = "Select an option..."
            st.session_state[f"ui_url_{i}"] = ""
        st.session_state.ui_folder_id = None
    else:
        preset = next(p for p in presets_usuario if p["datos"]["Nombre_Articulo"] == opcion)
        st.session_state.ui_nombre = preset["datos"]["Nombre_Articulo"]
        st.session_state.ui_precio = str(preset["datos"]["Precio"])
        
        # Parseamos los links guardados en la BD
        links_str = preset["datos"].get("Links", "[]")
        links_list = json.loads(links_str) if links_str else []
        
        for i in range(1, 6):
            if i <= len(links_list):
                st.session_state[f"ui_plat_{i}"] = links_list[i-1][0]
                st.session_state[f"ui_url_{i}"] = links_list[i-1][1]
            else:
                st.session_state[f"ui_plat_{i}"] = "Select an option..."
                st.session_state[f"ui_url_{i}"] = ""
        st.session_state.ui_folder_id = preset["datos"].get("ID_Carpeta_Drive")

st.selectbox("Saved Presets", nombres_presets, key="preset_selector", on_change=apply_preset)

# --- IMAGE UPLOADER / CLOUD NOTIFIER ---
if st.session_state.ui_folder_id:
    st.success("✅ Images loaded automatically from cloud storage.")
    imagenes_subidas = [] 
    usando_preset = True
else:
    imagenes_subidas = st.file_uploader(
        "Upload Images (Drag and drop supported)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    usando_preset = False

# --- TEXT INPUTS ---
nombre_articulo = st.text_input("Article Name", key="ui_nombre")
precio = st.text_input("Price", placeholder="e.g. 19.99", key="ui_precio")

# --- DYNAMIC LINKS ---
st.markdown("##### Links")
PLATAFORMAS = ["Select an option...", "USFans", "Hipobuy", "ACBuy", "Litbuy", "Mulebuy", "Hoobuy", "Vigorbuy"]
links_recopilados = []

for i in range(1, 6):
    col1, col2 = st.columns([1, 2])
    with col1:
        plat_seleccionada = st.selectbox(f"Platform {i}", PLATAFORMAS, key=f"ui_plat_{i}")
    with col2:
        esta_bloqueado = (plat_seleccionada == "Select an option...")
        link_url = st.text_input(f"URL {i}", disabled=esta_bloqueado, key=f"ui_url_{i}")
        
    if not esta_bloqueado and link_url.strip():
        links_recopilados.append((plat_seleccionada, link_url.strip()))

st.divider()

# --- SAVE OPTIONS & SUBMIT ---
guardar_preset = st.checkbox("Save this product as a preset (Overwrites if name already exists)")
enviado = st.button("Send to Telegram", use_container_width=True, type="primary")

# ------------------------------------------------------------------
# SUBMIT LOGIC
# ------------------------------------------------------------------
if enviado:
    _, servicio_drive = obtener_servicios_gcp()
    
    # 1. Image Resolution (Cloud vs Manual)
    if usando_preset:
        with st.spinner("Downloading images from cloud..."):
            imagenes_finales = descargar_imagenes_de_drive(servicio_drive, st.session_state.ui_folder_id)
            if not imagenes_finales:
                st.error("Error: The cloud folder is empty. Please clear the preset and re-upload the images manually.")
                st.stop()
    else:
        imagenes_finales = imagenes_subidas

    # 2. Validation
    missing_fields = []
    if not nombre_articulo: missing_fields.append("Article Name")
    if not precio: missing_fields.append("Price")
    if not links_recopilados: missing_fields.append("At least one link")
    if not imagenes_finales: missing_fields.append("At least one image")

    if missing_fields:
        st.warning("Missing required fields: " + ", ".join(missing_fields))
        st.stop()

    # 3. Limit Verification
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

    if usos_efectivos >= limite_diario:
        st.error(f"Daily limit reached ({limite_diario} posts). Please try again tomorrow.")
        st.stop()

    # 4. Telegram Publishing
    caption = construir_caption(nombre_articulo, precio, links_recopilados)

    with st.spinner("Publishing to Telegram..."):
        bot_token = st.secrets["telegram"]["bot_token"]
        channel_id = st.secrets["telegram"]["channel_id"]
        exito, error_msg = enviar_a_telegram(bot_token, channel_id, caption, imagenes_finales)

    if not exito:
        st.error(f"Error sending to Telegram: {error_msg}")
        st.stop()

    # 5. Saving Preset Logic (Drive & Sheets)
    if guardar_preset:
        with st.spinner("Saving preset to cloud..."):
            nombre_usuario = usuario.get('Nombre', 'User')
            folder_raiz = st.secrets["gdrive"]["folder_id"]
            
            # Buscamos si existe ya un preset con el mismo nombre para este usuario
            preset_existente = next((p for p in presets_usuario if p["datos"]["Nombre_Articulo"].strip().lower() == nombre_articulo.strip().lower()), None)
            
            # Obtenemos/Creamos la carpeta principal del usuario en Drive
            user_folder_id = obtener_o_crear_carpeta(servicio_drive, nombre_usuario, folder_raiz)
            
            # Si existía uno anterior con el mismo nombre, borramos la carpeta vieja
            if preset_existente:
                old_folder_id = preset_existente["datos"].get("ID_Carpeta_Drive")
                if old_folder_id:
                    borrar_archivo_o_carpeta(servicio_drive, old_folder_id)
            
            # Creamos la carpeta nueva del producto
            prod_folder_id = obtener_o_crear_carpeta(servicio_drive, nombre_articulo, user_folder_id)
            
            # Subimos las imágenes a Drive
            subir_imagenes_a_drive(servicio_drive, imagenes_finales, prod_folder_id)
            
            # Guardamos los textos en Sheets
            hoja_auth, hoja_presets = obtener_hojas()
            links_json = json.dumps(links_recopilados)
            guardar_preset_en_sheets(
                hoja_presets, 
                clave.strip(), 
                nombre_articulo, 
                precio, 
                links_json, 
                prod_folder_id, 
                fila_existente=preset_existente["fila"] if preset_existente else None
            )
            
            # Actualizamos la memoria interna (Session state) por si el usuario hace otro post sin recargar
            st.session_state.user_presets = obtener_presets(hoja_presets, clave.strip())

    # 6. Update Counter in Google Sheets
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
    st.success(f"Successfully published! You have {restantes} posts left today.")
