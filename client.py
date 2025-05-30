import json
import os
import logging
import requests
import configparser
from typing import Optional, Dict, Any, Tuple


config = configparser.ConfigParser()
if not os.path.exists("config.ini"):
    print("ERROR: Archivo config.ini no encontrado. El cliente no puede operar.")
    exit(1)
config.read("config.ini")

CLIENT_VALID_KEYS_FILE = config.get("client", "client_valid_keys_file", fallback="keys/valid.json")
SERVER_HOST = config.get("flask", "host", fallback="localhost") 
SERVER_PORT = config.getint("flask", "port", fallback=5000) 
SERVER_ENDPOINT_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/handle_request"

LOG_LEVEL_STR = config.get("logging", "level", fallback="INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - [CLIENT] - %(message)s')
logger = logging.getLogger(__name__)


def load_keys_from_local_file(file_path: str) -> list[str]:
    """
    Carga una lista de claves desde un archivo JSON local.
    Similar a la función del servidor, pero para uso del cliente.
    """
    if not os.path.exists(file_path):
        logger.warning(f"Archivo de claves del cliente no encontrado: {file_path}")
        return []
    try:
        with open(file_path, 'r') as f:
            keys = json.load(f)
            if not isinstance(keys, list):
                logger.warning(f"El archivo {file_path} no contiene una lista JSON válida. Devolviendo lista vacía.")
                return []
            return keys
    except (IOError, json.JSONDecodeError) as e:
        logger.error(f"Error al cargar claves desde {file_path}: {e}")
        return []

def get_available_key_from_local_list(
    local_valid_keys_file: str = CLIENT_VALID_KEYS_FILE
) -> Optional[str]:
    """
    Obtiene una clave de un solo uso de una lista local de claves válidas.
    Simula que el cliente ha recibido esta lista de la TTP.
    Para el prototipo, toma la primera clave del archivo.
    NOTA: Este cliente NO modifica el archivo, solo lee.
    """
    client_valid_keys = load_keys_from_local_file(local_valid_keys_file)
    if client_valid_keys:
        key_to_use = client_valid_keys[0]
        logger.info(f"Cliente usando clave obtenida de la lista local: {key_to_use}")
        return key_to_use
    else:
        logger.warning("Cliente: No hay claves disponibles en la lista local para usar.")
        return None

def make_request_to_server(
    server_url: str,
    one_time_key: str,
    payload_data: Optional[Dict[str, Any]] = None
) -> Tuple[Optional[str], Optional[int]]:
    """
    Realiza una petición HTTP POST al endpoint del servidor, enviando la clave
    de un solo uso y opcionalmente otros datos (payload) como JSON.

    Returns:
        Tuple[Optional[str], Optional[int]]: El texto de la respuesta y el código de estado.
    """
    headers = {'Content-Type': 'application/json'}
    data_to_send: Dict[str, Any] = {"key": one_time_key}

    if payload_data:
        data_to_send["payload"] = payload_data 

    logger.info(f"Enviando petición a {server_url} con clave: {one_time_key[:10]}... y payload: {payload_data is not None}")

    try:
        response = requests.post(server_url, json=data_to_send, headers=headers, timeout=10)
        logger.info(f"Respuesta recibida del servidor (Estado: {response.status_code})")
        return response.text, response.status_code
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"Error HTTP: {http_err} - Respuesta: {http_err.response.text if http_err.response else 'N/A'}")
        return (http_err.response.text if http_err.response else str(http_err),
                http_err.response.status_code if http_err.response else None)
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Error de conexión: {conn_err}")
        return str(conn_err), None
    except requests.exceptions.Timeout as timeout_err:
        logger.error(f"Timeout en la petición: {timeout_err}")
        return str(timeout_err), None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Error en la petición: {req_err}")
        return str(req_err), None
    except Exception as e:
        logger.error(f"Error inesperado durante la petición: {e}", exc_info=True)
        return str(e), None


def run_client_flow(
    server_endpoint_url: str = SERVER_ENDPOINT_URL,
    client_keys_file: str = CLIENT_VALID_KEYS_FILE
) -> None:
    """
    Orquesta el flujo completo del cliente:
    1. Obtiene una clave disponible.
    2. Realiza una petición al servidor con esa clave.
    3. Imprime la respuesta del servidor.
    """
    logger.info("--- Iniciando flujo del cliente ---")
    key_to_use = get_available_key_from_local_list(client_keys_file)

    if key_to_use:
        logger.info(f"Intentando usar la clave: {key_to_use}")
        mock_fhe_payload = {
            "fhe_data_blob": "simulacion_datos_cifrados_con_fhe_xxxxxxxxxxxx",
            "model_id": "modelo_predictivo_salud_v1.2",
            "user_metadata_param": "valor_ejemplo"
        }
        
        response_text, status_code = make_request_to_server(
            server_endpoint_url,
            key_to_use,
            payload_data=mock_fhe_payload
        )
        
        print("\n--- Respuesta del Servidor ---")
        if status_code is not None:
            print(f"Estado HTTP: {status_code}")
        if response_text is not None:
            try:
                response_json = json.loads(response_text)
                print(f"Cuerpo (JSON):\n{json.dumps(response_json, indent=2)}")
            except json.JSONDecodeError:
                print(f"Cuerpo (Texto):\n{response_text}")
        else:
            print("No se pudo obtener respuesta del servidor o hubo un error de conexión.")
        print("----------------------------\n")

    else:
        print("Cliente: No se pudo obtener una clave válida para usar del archivo local.")
        logger.warning("Flujo del cliente finalizado: no se obtuvo clave.")

    logger.info("--- Fin del flujo del cliente ---")


if __name__ == "__main__":

    keys_dir_client = os.path.dirname(CLIENT_VALID_KEYS_FILE)
    if keys_dir_client and not os.path.exists(keys_dir_client):
        logger.warning(f"El directorio de claves '{keys_dir_client}' no existe. "
                       f"El cliente podría no encontrar el archivo '{CLIENT_VALID_KEYS_FILE}'.")
    run_client_flow()