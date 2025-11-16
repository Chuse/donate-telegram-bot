import os
import requests
import json
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- 1. CONFIGURACIÓN INICIAL ---
# Las constantes numéricas de Klever Chain para el tipo de contrato.
CONTRACT_TYPES = {
    1: "Transfer",
    3: "AssetTrigger",
    15: "SmartContractCall",
    # Añade más si los necesitas
}

# Leer el token de acceso desde las variables de entorno de Render
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") 
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN no configurada. Por favor, añádela a las variables de entorno de Render.")

# Configuración del logging para ver errores en la consola del servidor
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- 2. LÓGICA DE KLEVER CHAIN ---

def get_transaction_details_klever(tx_hash: str) -> str:
    """
    Consulta los detalles de una transacción en Klever Chain, adaptando la extracción 
    de datos según el tipo de contrato.
    """
    KLEVER_API_BASE = "https://api.mainnet.klever.org/v1.0"
    endpoint = f"{KLEVER_API_BASE}/transaction/{tx_hash}"

    try:
        # Petición a la API de Klever
        response = requests.get(endpoint, timeout=10)
        response.raise_for_status() 
        data = response.json()
        
        transaction = data.get("data", {}).get("transaction")

        if not transaction:
           return f"⚠️ Transacción no encontrada o incompleta para el hash: {tx_hash}"

        # Extracción y mapeo de campos comunes
        contract_type_id = transaction.get("contractType", 999) 

        # Extrae el objeto payload
        payload = transaction.get("payload", {})
        # Intenta obtener el contractType del nivel superior (si existe)
        contract_type_id = transaction.get("contractType", 999)

        # --- DEBUG: INSPECCIÓN DE PAYLOAD ---
        if contract_type_id == 999:
           # Si el contractType no estaba en el nivel superior, mira en el payload
           if payload:
              # Aquí buscamos el tipo dentro del payload. Podría llamarse 'type', 'contractType' o similar.
              # Imprime el payload completo para ver su estructura.
             logger.info("DEBUG: PAYLOAD COMPLETO: %s", payload) 
            else:
              logger.info("DEBUG: Transacción sin Payload.")
        # ------------------------------------

        # --- 🚨 CÓDIGO DE DEPURACIÓN AÑADIDO 🚨 ---  
        print(f"DEBUG: contractType ID recibido de la API: {contract_type_id} (Tipo: {type(contract_type_id)})")
        # ----------------------------------------------
        
        contract_type = CONTRACT_TYPES.get(contract_type_id, "DESCONOCIDO")
        tx_status = "✅ ÉXITO" if transaction.get("status") == "success" else f"❌ FALLIDA / {transaction.get('status')}"
        
        # Variables para el mensaje final
        detalles_adicionales = ""
        sender = transaction.get("senderAddress", "N/A")
        
        # --- Lógica Condicional ---

        # --- CÓDIGO DE DEPURACIÓN ADICIONAL ---
        print(f"DEBUG: Tipo de contrato Mapeado: {contract_type}")
        # ----------------------------------------

        if contract_type == "Transfer":
            # Extrae detalles de una transferencia de tokens
            payload = transaction.get("payload", {})
            amount = payload.get("amount", 0)
            kda_symbol = payload.get("kda", "KLV")
            receiver = payload.get("receiver", "N/A")
            
            # Formato: Asume 6 decimales para la división
            display_amount = f"{int(amount) / 10**6:,.6f}" if isinstance(amount, (int, str)) and kda_symbol == "KLV" else amount
            
            detalles_adicionales = (
                f"\n**Monto:** {display_amount} {kda_symbol}"
                f"\n**Receptor:** `{receiver}`"
            )

        elif contract_type == "SmartContractCall":
            # Extrae detalles de una llamada a un Smart Contract (e.g., donación)
            payload = transaction.get("payload", {})
            data_field = payload.get("data", {})
            
            if data_field:
                parameters = data_field.get("parameters", [])
                
                detalles_adicionales = (
                    f"\n**Función SC:** {data_field.get('callType', 'N/A')}"
                )
                if parameters:
                    # Muestra hasta los primeros dos parámetros para evitar inundar el mensaje
                    for i, param in enumerate(parameters[:2]):
                        detalles_adicionales += (
                            f"\n**Parámetro {i+1} ({param.get('type', 'N/A')}):** `{param.get('value', 'N/A')}`"
                        )
            else:
                detalles_adicionales = "\n*Llamada SC sin datos de Payload.*"

        else:
            # Contratos no analizados (Freeze, Delegate, etc.)
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

    # Notificar al usuario (si el error ocurrió durante una interacción)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("Lo siento, hubo un error interno. Por favor, intenta de nuevo o revisa el hash.")
        except Exception:
            pass # Ignorar si no se puede enviar el mensaje de error

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
    application.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()
