"""
============================================================
 TELEGRAM POST PUBLISHER - Internal Streamlit App
============================================================
"""

import html
import json
from datetime import date, datetime

import gspread
import requests
import streamlit as st
from google.oauth2.service_account import Credentials

# ------------------------------------------------------------------
# PAGE CONFIGURATION & CSS
# ------------------------------------------------------------------
st.set_page_config(page_title="Telegram Publisher", layout="centered")

# CSS Injection for blue button and large dropzone
st.markdown("""
    <style>
    /* Light blue submit button */
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
    
    /* Larger dropzone for file uploader */
    [data-testid="stFileUploadDropzone"] {
        padding: 4rem !important;
        background-color: #F8F9FA !important;
        border: 2px dashed #CCCCCC !important;
    }
    </style>
""", unsafe_allow_html=True)

NOMBRE_PESTANA = "Usuarios" 

# ------------------------------------------------------------------
# GOOGLE SHEETS CONNECTION
# ------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def obtener_cliente_gsheets():
    alcances = ["https://www.googleapis.com/auth/spreadsheets"]
    credenciales_dict = dict(st.secrets["gcp_service_account"])
    credenciales = Credentials.from_service_account_info(credenciales_dict, scopes=alcances)
    return gspread.authorize(credenciales)

def obtener_hoja():
    cliente = obtener_cliente_gsheets()
    id_hoja = st.secrets["gsheets"]["sheet_id"]
    libro = cliente.open_by_key(id_hoja)
    return libro.worksheet(NOMBRE_PESTANA)

def obtener_mapa_columnas(hoja):
    encabezados = hoja.row_values(1)
    return {nombre.strip(): idx + 1 for idx, nombre in enumerate(encabezados)}

def buscar_usuario(hoja, clave):
    registros = hoja.get_all_records()
    for i, fila in enumerate(registros):
        if str(fila.get("Clave", "")).strip() == clave:
            return i + 2, fila
    return None, None

def parsear_fecha(valor):
    if not valor:
        return None
    valor = str(valor).strip()
    formatos_posibles = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]
    for formato in formatos_posibles:
        try:
            return datetime.strptime(valor, formato).date()
        except ValueError:
            continue
    return None

def actualizar_uso(hoja, fila, col_map, nuevos_usos, fecha_hoy_str):
    actualizaciones = [
        {
            "range": gspread.utils.rowcol_to_a1(fila, col_map["Usos_Hoy"]),
            "values": [[nuevos_usos]],
        },
        {
            "range": gspread.utils.rowcol_to_a1(fila, col_map["Ultima_Fecha"]),
            "values": [[fecha_hoy_str]],
        },
    ]
    hoja.batch_update(actualizaciones)


# ------------------------------------------------------------------
# TELEGRAM CAPTION CONSTRUCTION
# ------------------------------------------------------------------
def construir_caption(nombre, precio, links_data):
    texto = f"<b>{html.escape(nombre)}</b>\n\n"
    texto += f"<b>Price:</b> {html.escape(precio)}\n\n"
    
    # Creates an HTML hyperlink for each link: <a href="URL">Platform</a>
    for plataforma, url in links_data:
        texto += f"🔗 <a href='{html.escape(url, quote=True)}'>{html.escape(plataforma)}</a>\n"
        
    return texto


# ------------------------------------------------------------------
# TELEGRAM SEND LOGIC
# ------------------------------------------------------------------
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
# UI & LOGIC
# ------------------------------------------------------------------

# 1. Pre-requisite authentication window
clave = st.text_input("Access Key", type="password", placeholder="Enter your key and press Enter")

if not clave:
    st.stop()  # Stops execution until a key is typed

# Only run the Google Sheets query if the key is new or not yet verified
if "current_key" not in st.session_state or st.session_state.current_key != clave:
    with st.spinner("Verifying access key..."):
        try:
            hoja_auth = obtener_hoja()
            col_map_auth = obtener_mapa_columnas(hoja_auth)
            fila_auth, usuario_auth = buscar_usuario(hoja_auth, clave.strip())
            
            st.session_state.current_key = clave
            if usuario_auth is None:
                st.session_state.is_authenticated = False
                st.session_state.user_data = None
            else:
                st.session_state.is_authenticated = True
                st.session_state.user_data = usuario_auth
                st.session_state.row_index = fila_auth
                st.session_state.col_map = col_map_auth
        except Exception as error:
            st.error(f"Could not connect to Google Sheets: {error}")
            st.stop()

if not st.session_state.get("is_authenticated"):
    st.error("Invalid access key. Please try again.")
    st.stop()

# Load cached user data
usuario = st.session_state.user_data
fila = st.session_state.row_index
col_map = st.session_state.col_map

st.success(f"Access granted. Welcome, {usuario.get('Nombre', 'User')}!")
st.divider()


# 2. Main Post Customization
st.subheader("Post Customization")

imagenes = st.file_uploader(
    "Upload Images (Drag and drop supported)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

nombre_articulo = st.text_input("Article Name")
precio = st.text_input("Price", placeholder="e.g. 19.99")

# Dynamic Link Section
st.markdown("##### Links")
PLATAFORMAS = ["Select an option...", "USFans", "Hipobuy", "ACBuy", "Litbuy", "Mulebuy", "Hoobuy", "Vigorbuy"]
links_recopilados = []

for i in range(1, 6):
    col1, col2 = st.columns([1, 2])
    with col1:
        plat_seleccionada = st.selectbox(f"Platform {i}", PLATAFORMAS, key=f"plat_{i}")
    with col2:
        # The text input is disabled if "Select an option..." is chosen
        esta_bloqueado = (plat_seleccionada == "Select an option...")
        link_url = st.text_input(f"URL {i}", disabled=esta_bloqueado, key=f"url_{i}")
        
    # If a valid platform is chosen and the user wrote a link, save it
    if not esta_bloqueado and link_url.strip():
        links_recopilados.append((plat_seleccionada, link_url.strip()))

st.divider()

# Submit Button
enviado = st.button("Send to Telegram", use_container_width=True, type="primary")

# 3. Submit Logic
if enviado:
    missing_fields = []
    if not nombre_articulo: missing_fields.append("Article Name")
    if not precio: missing_fields.append("Price")
    if not links_recopilados: missing_fields.append("At least one link")
    if not imagenes: missing_fields.append("At least one image")

    if missing_fields:
        st.warning("Missing required fields: " + ", ".join(missing_fields))
        st.stop()

    # --- Limit Verification ---
    hoy = date.today()
    fecha_guardada = parsear_fecha(usuario.get("Ultima_Fecha"))

    try:
        usos_hoy_actual = int(usuario.get("Usos_Hoy") or 0)
    except ValueError:
        usos_hoy_actual = 0

    try:
        valor_limite = usuario.get("Límite_Diario") or usuario.get("Limite_Diario") or 0
        limite_diario = int(valor_limite)
    except ValueError:
        limite_diario = 0

    usos_efectivos = 0 if fecha_guardada != hoy else usos_hoy_actual

    if usos_efectivos >= limite_diario:
        st.error(f"Daily limit reached ({limite_diario} posts). Please try again tomorrow.")
        st.stop()

    # --- Publishing ---
    caption = construir_caption(nombre_articulo, precio, links_recopilados)

    with st.spinner("Publishing to Telegram..."):
        bot_token = st.secrets["telegram"]["bot_token"]
        channel_id = st.secrets["telegram"]["channel_id"]
        exito, error_msg = enviar_a_telegram(bot_token, channel_id, caption, imagenes)

    if not exito:
        st.error(f"Error sending to Telegram: {error_msg}")
        st.stop()

    # --- Updating Counter in Google Sheets ---
    try:
        # Re-fetch connection just for writing to avoid timeout issues
        hoja_actualizar = obtener_hoja() 
        actualizar_uso(hoja_actualizar, fila, col_map, usos_efectivos + 1, hoy.strftime("%Y-%m-%d"))
    except Exception as error:
        st.warning(
            f"Published to Telegram, but could not update the counter in Sheets: {error}"
        )
        st.stop()

    restantes = limite_diario - (usos_efectivos + 1)
    st.success(f"Successfully published! You have {restantes} posts left today.")
