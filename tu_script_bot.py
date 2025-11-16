import os
import requests
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- 1. CONFIGURACIÓN INICIAL Y DEPENDENCIAS ---

# Las constantes numéricas de Klever Chain (ya no se usan para la extracción, pero se mantienen como referencia)
# La API nos está devolviendo ahora el tipo como una cadena de texto dentro de la lista 'contract'.
# Este diccionario ya NO es necesario, pero lo mantenemos para claridad.
CONTRACT_TYPES = {
    1: "Transfer",
    3: "AssetTrigger",
    15: "SmartContractCall",
}

# Leer el token de acceso desde las variables de entorno de Render
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") 
if not TELEGRAM_BOT_TOKEN:
    # Esto lanzará un error si el token no está configurado en Render
    raise ValueError("TELEGRAM_BOT_TOKEN no configurada. Por favor, añádela a las variables de entorno de Render.")

# Configuración del logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- 2. LÓGICA DE KLEVER CHAIN ---

def get_transaction_details_klever(tx_hash: str) -> str:
    """
    Consulta los detalles de una transacción en Klever Chain, adaptando la extracción 
    de datos a la estructura JSON correcta que usa la lista 'contract'.
    """
    KLEVER_API_BASE = "https://api.mainnet.klever.org/v1.0"
    endpoint = f"{KLEVER_API_BASE}/transaction/{tx_hash}"

    try:
        # Petición a la API de Klever
        response = requests.get(endpoint, timeout=10)
        response.raise_for_status() 
        data = response.json()
        
        # El objeto de la transacción principal para tu API está bajo 'data.transaction'
        # o a veces 'data', dependiendo del endpoint, lo hacemos seguro:
        # Buscamos en 'data.transaction' si existe, sino, asumimos que 'data' es la transacción.
        transaction = data.get("data", {}).get("transaction") or data.get("data")

        if not transaction:
             return f"⚠️ Transacción no encontrada o incompleta para el hash: {tx_hash}"

        # --- EXTRACCIÓN DE CAMPOS PRINCIPALES (Estructura de la última depuración) ---
        
        # Estos campos están en el nivel superior de tu JSON
        sender = transaction.get("sender", "N/A")
        tx_status = "✅ ÉXITO" if transaction.get("status") == "success" else f"❌ FALLIDA / {transaction.get('status')}"
        
        # 2. PROCESAMIENTO DEL CONTRATO (LISTA)
        contracts = transaction.get("contract", [])
        detalles_adicionales = ""
        contract_type = "DESCONOCIDO"

        # Asumimos que la lista 'contract' tiene al menos un elemento [0]
        if contracts:
            contract_info = contracts[0]
            contract_type = contract_info.get("typeString", "N/A")  # Ej: "TransferContractType"
            parameter = contract_info.get("parameter", {})

            if contract_type == "TransferContractType":
                # Extracción de detalles de Transferencia (ej: KFI)
                amount = parameter.get("amount", 0)
                kda_symbol = parameter.get("assetId", "KLV")
                receiver = parameter.get("toAddress", "N/A")

                # Formato: Usamos el amount tal cual (se asume que la API lo normaliza)
                detalles_adicionales = (
                    f"\n**Monto:** {amount} {kda_symbol}"
                    f"\n**Receptor:** `{receiver}`"
                )
            elif contract_type == "SmartContractCallType":
                 # Lógica adaptada para llamadas SC si la API usa esta estructura
                 call_data = parameter.get("data", {})
                 detalles_adicionales = (
                    f"\n**Función SC:** {call_data.get('callType', 'N/A')}"
                 )
            else:
                 detalles_adicionales = f"\n*Contrato de Tipo {contract_type}: No analizado.*"
        
        # --- Mensaje Final ---
        message = (
            f"🔍 **Detalles de Transacción en Klever Chain**\n"
            f"----------------------------------------\n"
            f"**Hash (ID):** `{tx_hash[:10]}...`\n"
            f"**Estado:** {tx_status}\n"
            f"**Tipo de Contrato:** **{contract_type}**"
            f"\n**Emisor (Principal):** `{sender}`"
            f"{detalles_adicionales}"
            f"\n\n**Explorer:** [Ver en KleverScan](https://kleverscan.org/tx/{tx_hash})\n"
        )
        return message

    except requests.exceptions.RequestException as e:
        logger.error("Error de conexión al API de Klever: %s", e)
        return f"🚨 Error de conexión al API de Klever."
    except Exception as e:
        # Captura errores de JSON malformado o fallos de indexación
        logger.error("Error inesperado al analizar la transacción: %s", e)
        return f"❌ Ocurrió un error inesperado al analizar la transacción: {e}"


# --- 3. MANEJADORES DE COMANDOS DE TELEGRAM ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /start."""
    await update.message.reply_text("¡Hola! Soy tu bot para consultar transacciones de Klever Chain. Usa /tx <HASH> para empezar.")

async def tx_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja el comando /tx y llama a la lógica de Klever."""
    
    try:
        tx_hash = context.args[0].strip()
        if len(tx_hash) != 64:
             await update.message.reply_text("El hash de la transacción debe tener exactamente 64 caracteres.")
             return
             
    except (IndexError, AttributeError):
        await update.message.reply_text("Uso incorrecto. Por favor, usa: `/tx <HASH_DE_TRANSACCIÓN>`", parse_mode='Markdown')
        return

    # Llama a la función de Klever
    response_text = get_transaction_details_klever(tx_hash)
    
    # Envía la respuesta al chat
    await update.message.reply_text(response_text, parse_mode='Markdown')


# --- 4. MANEJADOR DE ERRORES GENERAL ---

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja los errores generados por la aplicación y los registra."""
    
    # Registra el error completo en el log de Render
    logger.error("Excepción al procesar la actualización: %s", context.error, exc_info=True)

    # El error de conflicto de polling se maneja silenciosamente
    if "Conflict" in str(context.error):
        logger.warning("Conflicto de Polling detectado y manejado. Otra instancia está activa.")
        return
        
    # Notificar al usuario (si el error ocurrió durante una interacción)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("Lo siento, hubo un error interno. Por favor, intenta de nuevo o revisa el hash.")
        except Exception:
            pass 

# --- 5. FUNCIÓN PRINCIPAL DE EJECUCIÓN ---

def main() -> None:
    """Inicia el bot con el método polling."""
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Registra los manejadores
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("tx", tx_command))
    application.add_error_handler(error_handler) # Registra el manejador de errores

    # Inicia la escucha (polling) del bot
    logger.info("Bot iniciado. Escuchando nuevos mensajes...")
    application.run_polling(poll_interval=1.0) # El poll_interval puede ser ajustado

if __name__ == "__main__":
    main()
