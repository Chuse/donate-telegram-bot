import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import os
import logging # Necesario para la comprobación

# ...

# --- 1. CONFIGURACIÓN ---
# Lee la variable desde el entorno de Render
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


# Esta comprobación es vital para detener el script si la variable no se encontró
if not TELEGRAM_BOT_TOKEN:
    # Registra el error y lo lanza para que Render lo vea
    logging.error("La variable de entorno TELEGRAM_BOT_TOKEN no está configurada.")
    raise ValueError("La variable de entorno TELEGRAM_BOT_TOKEN no está configurada.")

# Configuración del logging para ver errores en la consola del servidor
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. LÓGICA DE KLEVER (Función del ejemplo anterior) ---
def get_transaction_details_klever(tx_hash: str) -> str:
    """Consulta los detalles de una transacción en la Klever Blockchain."""
    KLEVER_API_BASE = "https://api.mainnet.klever.org/v1.0"
    endpoint = f"{KLEVER_API_BASE}/transaction/{tx_hash}"

    try:
        response = requests.get(endpoint, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # ... (La lógica de procesamiento del JSON y formateo del mensaje es la misma) ...
        transaction = data.get("data", {}).get("transaction")

        if not transaction:
             return f"⚠️ Transacción no encontrada o incompleta para el hash: {tx_hash}"

        tx_status = "✅ ÉXITO" if transaction.get("status") == "success" else f"❌ FALLIDA / {transaction.get('status')}"
        contract_type = transaction.get("contractType") 
        sender = transaction.get("senderAddress")
        receiver = transaction.get("receiverAddress", "N/A")

        message = (
            f"🔍 **Detalles de Transacción en Klever Chain**\n"
            f"----------------------------------------\n"
            f"**Hash (ID):** `{tx_hash[:10]}...`\n"
            f"**Estado:** {tx_status}\n"
            f"**Tipo de Contrato:** {contract_type}\n"
            f"**Emisor:** `{sender}`\n"
            f"**Receptor:** `{receiver}`\n"
            f"**Explorer:** [Ver en KleverScan](https://kleverscan.org/tx/{tx_hash})\n"
        )
        return message

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión al API de Klever: {e}")
        return f"🚨 Error de conexión al API de Klever."

# --- 3. MANEJADORES DE COMANDOS DE TELEGRAM ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /start."""
    await update.message.reply_text("¡Hola! Soy tu bot para consultar transacciones de Klever Chain. Usa /tx <HASH> para empezar.")

async def tx_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /tx y llama a la lógica de Klever."""
    logger.info(f"Comando /tx recibido de {update.effective_user.username}")
    
    try:
        # Los argumentos del comando están en context.args
        tx_hash = context.args[0].strip()
        if len(tx_hash) != 64:
             await update.message.reply_text("El hash de la transacción debe tener 64 caracteres.")
             return
             
    except (IndexError, AttributeError):
        await update.message.reply_text("Uso incorrecto. Por favor, usa: `/tx <HASH_DE_TRANSACCIÓN>`", parse_mode='Markdown')
        return

    # Llama a la función de Klever
    response_text = get_transaction_details_klever(tx_hash)
    
    # Envía la respuesta al chat
    await update.message.reply_text(response_text, parse_mode='Markdown')

# --- 4. FUNCIÓN PRINCIPAL DE EJECUCIÓN ---
def main() -> None:
    """Inicia el bot."""
    # Crea la aplicación del Bot
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Registra los manejadores de comandos
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("tx", tx_command))

    # Inicia la escucha (polling) del bot
    logger.info("Bot iniciado. Escuchando nuevos mensajes...")
    application.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    if TELEGRAM_BOT_TOKEN == "TU_TOKEN_DE_TELEGRAM":
        print("🛑 ERROR: ¡Recuerda reemplazar 'TU_TOKEN_DE_TELEGRAM' con tu token real!")
    else:
        main()
