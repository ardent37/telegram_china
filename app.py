"""
============================================================
 PUBLICADOR DE POSTS EN TELEGRAM - App interna en Streamlit
============================================================

Qué hace esta app:
1. Pide una "Clave de acceso" y la valida contra una hoja de
   Google Sheets (pestaña "Usuarios").
2. Comprueba el límite diario de publicaciones de esa clave.
3. Si todo es correcto, publica un álbum de fotos + texto
   formateado en un canal de Telegram usando sendMediaGroup.
4. Actualiza el contador de usos en Google Sheets.

Todas las credenciales (token del bot, ID del canal y las
credenciales de la Service Account de Google) se leen desde
st.secrets. Nunca están escritas en este archivo.
"""

import html
import json
from datetime import date, datetime

import gspread
import requests
import streamlit as st
from google.oauth2.service_account import Credentials

# ------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# ------------------------------------------------------------------
st.set_page_config(page_title="Publicador Telegram", page_icon="📤", layout="centered")

NOMBRE_PESTANA = "Usuarios"  # Nombre exacto de la pestaña en el Google Sheet


# ------------------------------------------------------------------
# CONEXIÓN A GOOGLE SHEETS
# ------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def obtener_cliente_gsheets():
    """
    Crea (y cachea en memoria) el cliente autorizado de gspread,
    usando las credenciales de la Service Account guardadas en
    st.secrets["gcp_service_account"].
    """
    alcances = ["https://www.googleapis.com/auth/spreadsheets"]
    credenciales_dict = dict(st.secrets["gcp_service_account"])
    credenciales = Credentials.from_service_account_info(credenciales_dict, scopes=alcances)
    return gspread.authorize(credenciales)


def obtener_hoja():
    """Abre el Google Sheet (por su ID guardado en secrets) y devuelve la pestaña 'Usuarios'."""
    cliente = obtener_cliente_gsheets()
    id_hoja = st.secrets["gsheets"]["sheet_id"]
    libro = cliente.open_by_key(id_hoja)
    return libro.worksheet(NOMBRE_PESTANA)


def obtener_mapa_columnas(hoja):
    """
    Lee la fila de encabezados (fila 1) y construye un diccionario
    {nombre_columna: número_de_columna}. Así no dependemos de un
    orden fijo de columnas para escribir datos.
    """
    encabezados = hoja.row_values(1)
    return {nombre.strip(): idx + 1 for idx, nombre in enumerate(encabezados)}


def buscar_usuario(hoja, clave):
    """
    Busca 'clave' en la columna 'Clave'.
    Devuelve (numero_de_fila_en_la_hoja, dict_con_los_datos_de_la_fila).
    Si no la encuentra, devuelve (None, None).
    """
    registros = hoja.get_all_records()  # Lista de dicts, una por fila de datos
    for i, fila in enumerate(registros):
        if str(fila.get("Clave", "")).strip() == clave:
            # +2 porque: la fila 1 es el encabezado, y enumerate() empieza en 0
            return i + 2, fila
    return None, None


def parsear_fecha(valor):
    """
    Convierte el valor de la celda 'Ultima_Fecha' a un objeto date.
    Soporta que gspread devuelva el valor como texto en distintos
    formatos habituales. Si está vacío o no se puede interpretar,
    devuelve None (se tratará como "día distinto", forzando el reseteo).
    """
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
    """
    Actualiza en una sola llamada a la API ('Usos_Hoy' y 'Ultima_Fecha')
    para la fila del usuario que acaba de publicar.
    """
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
# CONSTRUCCIÓN DEL TEXTO (CAPTION) PARA TELEGRAM
# ------------------------------------------------------------------
def construir_caption(nombre, precio, link1, link2):
    """
    Genera el texto formateado en HTML (negritas + emojis) que irá
    como caption de la primera foto del álbum.
    Se escapan los campos para evitar que caracteres como < o &
    rompan el formato HTML del mensaje.
    """
    texto = f"🛍️ <b>{html.escape(nombre)}</b>\n\n"
    texto += f"💰 <b>Precio:</b> {html.escape(precio)}\n\n"
    texto += f"🔗 <b>Link 1:</b> {html.escape(link1, quote=False)}\n"
    if link2:
        texto += f"🔗 <b>Link 2:</b> {html.escape(link2, quote=False)}\n"
    return texto


# ------------------------------------------------------------------
# ENVÍO A TELEGRAM (sendMediaGroup / sendPhoto)
# ------------------------------------------------------------------
def enviar_a_telegram(bot_token, chat_id, caption, imagenes):
    """
    Envía las imágenes (en memoria, sin tocar disco) al canal de Telegram.

    - Si hay 2 o más imágenes: usa sendMediaGroup para publicar un
      álbum. El 'caption' con el texto formateado va ÚNICAMENTE en
      la primera imagen del array; el resto se envían sin caption.
    - Si hay exactamente 1 imagen: la API de Telegram no permite
      sendMediaGroup con un solo elemento (mínimo 2), así que en ese
      caso se usa sendPhoto con el caption normalmente.

    Devuelve una tupla (exito: bool, mensaje_error: str).
    """
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
                    # El caption formateado SOLO va en la primera imagen
                    item["caption"] = caption
                    item["parse_mode"] = "HTML"
                media.append(item)
                # Se pasa el archivo directamente desde memoria (BytesIO interno de Streamlit)
                files[clave_archivo] = (archivo.name, archivo.getvalue(), archivo.type)

            data = {"chat_id": chat_id, "media": json.dumps(media)}
            respuesta = requests.post(url, data=data, files=files, timeout=60)

        resultado = respuesta.json()
        if resultado.get("ok"):
            return True, ""
        return False, resultado.get("description", "Error desconocido de Telegram")

    except requests.exceptions.RequestException as error:
        return False, f"Error de conexión con Telegram: {error}"


# ------------------------------------------------------------------
# INTERFAZ (UI)
# ------------------------------------------------------------------
st.title("📤 Publicador de Posts en Telegram")
st.caption("Herramienta interna — introduce tu clave de acceso para publicar en el canal.")

with st.form("form_post", clear_on_submit=False):
    st.subheader("🔑 Acceso")
    clave = st.text_input("Clave de acceso", type="password", placeholder="Ej: MATEO-123")

    st.subheader("📝 Datos del artículo")
    nombre_articulo = st.text_input("Nombre del artículo")
    precio = st.text_input("Precio", placeholder="Ej: 19,99 €")
    link1 = st.text_input("Link 1")
    link2 = st.text_input("Link 2 (opcional)")

    st.subheader("🖼️ Imágenes")
    imagenes = st.file_uploader(
        "Sube una o varias imágenes",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    enviado = st.form_submit_button("🚀 Enviar a Telegram", use_container_width=True)


# ------------------------------------------------------------------
# LÓGICA AL PULSAR "ENVIAR A TELEGRAM"
# ------------------------------------------------------------------
if enviado:
    # --- 0. Validar que estén todos los campos obligatorios ---
    campos_faltantes = []
    if not clave:
        campos_faltantes.append("Clave de acceso")
    if not nombre_articulo:
        campos_faltantes.append("Nombre del artículo")
    if not precio:
        campos_faltantes.append("Precio")
    if not link1:
        campos_faltantes.append("Link 1")
    if not imagenes:
        campos_faltantes.append("Al menos una imagen")

    if campos_faltantes:
        st.warning("⚠️ Faltan datos obligatorios: " + ", ".join(campos_faltantes))
        st.stop()

    # --- 1. Buscar la clave en Google Sheets ---
    with st.spinner("Verificando clave de acceso..."):
        try:
            hoja = obtener_hoja()
            col_map = obtener_mapa_columnas(hoja)
            fila, usuario = buscar_usuario(hoja, clave.strip())
        except Exception as error:
            st.error(f"❌ No se pudo conectar con Google Sheets: {error}")
            st.stop()

    if usuario is None:
        st.error("❌ Clave de acceso no válida.")
        st.stop()

    # --- 2. Comprobar Ultima_Fecha y resetear Usos_Hoy si es un día distinto ---
    hoy = date.today()
    fecha_guardada = parsear_fecha(usuario.get("Ultima_Fecha"))

    try:
        usos_hoy_actual = int(usuario.get("Usos_Hoy") or 0)
    except ValueError:
        usos_hoy_actual = 0

    try:
        limite_diario = int(usuario.get("Límite_Diario") or 0)
    except ValueError:
        limite_diario = 0

    usos_efectivos = 0 if fecha_guardada != hoy else usos_hoy_actual

    # --- 3. Comprobar el límite diario ---
    if usos_efectivos >= limite_diario:
        st.error(f"🚫 Límite diario alcanzado ({limite_diario} publicaciones). Vuelve mañana.")
        st.stop()

    # --- 4. Construir el mensaje y publicar en Telegram ---
    caption = construir_caption(nombre_articulo, precio, link1, link2)

    with st.spinner("Publicando en Telegram..."):
        bot_token = st.secrets["telegram"]["bot_token"]
        channel_id = st.secrets["telegram"]["channel_id"]
        exito, error_msg = enviar_a_telegram(bot_token, channel_id, caption, imagenes)

    if not exito:
        st.error(f"❌ Error al enviar a Telegram: {error_msg}")
        st.stop()

    # --- Actualizar el contador en Google Sheets ---
    try:
        actualizar_uso(hoja, fila, col_map, usos_efectivos + 1, hoy.strftime("%Y-%m-%d"))
    except Exception as error:
        st.warning(
            f"✅ Se publicó en Telegram, pero no se pudo actualizar el contador en Sheets: {error}"
        )
        st.stop()

    restantes = limite_diario - (usos_efectivos + 1)
    nombre_usuario = usuario.get("Nombre", "")
    st.success(f"✅ ¡Publicado con éxito, {nombre_usuario}! Te quedan {restantes} publicaciones hoy.")
    st.balloons()
