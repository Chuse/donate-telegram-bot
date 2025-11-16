import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import os
import logging # Necesario para la comprobación

# Mapeo de constantes de contrato de Klever Chain
CONTRACT_TYPES = {
    1: "Transfer",
    3: "AssetTrigger",
    15: "SmartContractCall",

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
    """
    Consulta los detalles de una transacción, adaptando la extracción de datos
    según el tipo de contrato (contractType).
    """
    KLEVER_API_BASE = "https://api.mainnet.klever.org/v1.0"
    endpoint = f"{KLEVER_API_BASE}/transaction/{tx_hash}"

    try:
        response = requests.get(endpoint, timeout=10)
        response.raise_for_status() 
        data = response.json()
        
        transaction = data.get("data", {}).get("transaction")

        if not transaction:
             return f"⚠️ Transacción no encontrada o incompleta para el hash: {tx_hash}"

        # 1. Extraer los campos comunes
        contract_type = transaction.get("contractType", "DESCONOCIDO")
        tx_status = "✅ ÉXITO" if transaction.get("status") == "success" else f"❌ FALLIDA / {transaction.get('status')}"
        
        # Variables que almacenarán la información condicional
        detalles_adicionales = ""
        sender = transaction.get("senderAddress", "N/A")
        
        # 2. Lógica Condicional (if/elif/else)

        if contract_type == "Transfer":
            # --- TIPO 1: TRANSFERENCIA SIMPLE (KLV o KDA) ---
            
            # Los datos clave están a nivel superior o en el payload/data
            payload = transaction.get("payload", {})
            amount = payload.get("amount", "0")
            kda_symbol = payload.get("kda", "KLV")
            receiver = payload.get("receiver", "N/A")
            
            # Construir el detalle específico para Transfer
            detalles_adicionales = (
                f"\n**Cantidad:** {int(amount) / 10**6} {kda_symbol}"
                f"\n**Receptor:** `{receiver}`"
            )

        elif contract_type == "SmartContractCall":
            # --- TIPO 2: LLAMADA A SMART CONTRACT ---
            
            # El sender real (usuario) puede estar en 'senderAddress' o anidado
            payload = transaction.get("payload", {})
            data_field = payload.get("data", {})
            
            # Buscar el sender real (que hizo la llamada)
            if data_field:
                # La dirección del usuario (sender real) suele ser el primer parámetro
                # en el array 'parameters' (es una suposición basada en la estructura de Klever)
                parameters = data_field.get("parameters", [])
                
                # Ejemplo de extracción del primer parámetro si existe
                if parameters:
                    primer_param_valor = parameters[0].get("value", "N/A")
                    primer_param_tipo = parameters[0].get("type", "Texto")
                    
                    detalles_adicionales = (
                        f"\n**Función SC:** {data_field.get('callType', 'N/A')}"
                        f"\n**Parámetro 1 ({primer_param_tipo}):** `{primer_param_valor}`"
                    )
                else:
                    detalles_adicionales = "\n**Sin Parámetros SC Adicionales**"

        else:
            # --- OTROS TIPOS: Freeze, Stake, etc. ---
            detalles_adicionales = "\n*Contrato Desconocido o con estructura no analizada.*"
            
        # 3. Construir el mensaje final para Telegram
        message = (
            f"🔍 **Detalles de Transacción en Klever Chain**\n"
            f"----------------------------------------\n"
            f"**Hash (ID):** `{tx_hash[:10]}...`\n"
            f"**Estado:** {tx_status}\n"
            f"**Tipo de Contrato:** **{contract_type}**"
            f"\n**Emisor (Principal):** `{sender}`"
            f"{detalles_adicionales}" # Se insertan los detalles específicos aquí
            f"\n\n**Explorer:** [Ver en KleverScan](https://kleverscan.org/tx/{tx_hash})\n"
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
