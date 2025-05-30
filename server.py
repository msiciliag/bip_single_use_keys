import json
import os
import logging
from typing import List, Optional, Tuple
import configparser
from flask import Flask, request, jsonify
from bip_utils import (
    Bip39MnemonicGenerator, Bip39SeedGenerator, Bip44, Bip44Coins,
    Bip44Changes
)

config = configparser.ConfigParser()
if not os.path.exists("config.ini"):
    logging.warning("Archivo config.ini no encontrado. Usando valores por defecto.")
config.read("config.ini")


class KeyService:
    def __init__(self, app_config: configparser.ConfigParser):
        self.config = app_config
        self._load_config_parameters()
        self._setup_logging()
        self._ensure_keys_directory_exists()

        self.master_xpub: Optional[str] = None
        self.valid_keys: List[str] = []
        self.used_keys: List[str] = []

        self._initialize_service_state()

    def _load_config_parameters(self):
        """Carga los parámetros de configuración específicos del servicio."""
        self.server_xpub_file = self.config.get("server", "server_xpub_file", fallback="keys/server_xpub.txt")
        self.valid_keys_file = self.config.get("server", "valid_keys_file", fallback="keys/valid.json")
        self.used_keys_file = self.config.get("server", "used_keys_file", fallback="keys/used.json")
        self.initial_key_batch_size = self.config.getint("server", "initial_key_batch_size", fallback=100)
        self.crypto_validation_window_size = self.config.getint("server", "crypto_validation_window_size", fallback=1000)
        self.default_account_index = self.config.getint("server", "default_account_index", fallback=0)
        self.max_index_to_check_crypto = self.config.getint("server", "max_index_to_check_crypto", fallback=1000) # Nueva config

    def _setup_logging(self):
        """Configura el logging para la aplicación."""
        log_level_str = self.config.get("logging", "level", fallback="INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')
        self.logger = logging.getLogger(self.__class__.__name__) 

    def _ensure_keys_directory_exists(self):
        """Asegura que el directorio de claves exista."""
        keys_dir = os.path.dirname(self.server_xpub_file) 
        if keys_dir and not os.path.exists(keys_dir):
            try:
                os.makedirs(keys_dir)
                self.logger.info(f"Directorio '{keys_dir}' creado.")
            except OSError as e:
                self.logger.error(f"Error al crear el directorio '{keys_dir}': {e}")
                raise

    def _generate_and_save_master_xpub(self) -> str:
        """Genera y guarda la xPub maestra del servidor (a nivel de cuenta BIP44, m/44'/1'/account').
        
        La xPub generada corresponderá al nodo de cuenta (m/44'/1'/account') para poder derivar
        posteriormente tanto la cadena externa (m/44'/1'/account'/0) como la interna (m/44'/1'/account'/1).
        """
        mnemonic = Bip39MnemonicGenerator().FromWordsNumber(12)
        self.logger.info(f"Nueva mnemónica generada (¡GUARDAR EN LUGAR SEGURO!): {mnemonic.ToStr()}")
        seed_bytes = Bip39SeedGenerator(mnemonic.ToStr()).Generate()
        bip44_mst = Bip44.FromSeed(seed_bytes, Bip44Coins.BITCOIN_TESTNET)
        bip44_acc_node = bip44_mst.Purpose().Coin().Account(self.default_account_index)
        master_xpub = bip44_acc_node.PublicKey().ToExtended()

        try:
            with open(self.server_xpub_file, "w") as f:
                f.write(master_xpub)
            self.logger.info(f"xPub maestra de CUENTA (BIP44 m/44'/1'/{self.default_account_index}') guardada en: {self.server_xpub_file}")
        except IOError as e:
            self.logger.error(f"Error al guardar la xPub maestra de cuenta en {self.server_xpub_file}: {e}")
            raise
        return master_xpub

    def _load_master_xpub(self) -> Optional[str]:
        """Carga la xPub maestra desde el archivo."""
        if os.path.exists(self.server_xpub_file):
            try:
                with open(self.server_xpub_file, "r") as f:
                    return f.read().strip()
            except IOError as e:
                self.logger.error(f"Error al leer la xPub maestra de {self.server_xpub_file}: {e}")
        return None

    def _load_keys_from_file(self, file_path: str) -> List[str]:
        """Carga claves desde un archivo JSON."""
        if not os.path.exists(file_path):
            return []
        try:
            with open(file_path, 'r') as f:
                keys = json.load(f)
                return keys if isinstance(keys, list) else []
        except (IOError, json.JSONDecodeError) as e:
            self.logger.error(f"Error al cargar claves desde {file_path}: {e}")
            return []

    def _save_keys_to_file(self, keys_list: List[str], file_path: str) -> bool:
        """Guarda claves en un archivo JSON."""
        try:
            with open(file_path, 'w') as f:
                json.dump(keys_list, f, indent=4)
            return True
        except IOError as e:
            self.logger.error(f"Error al guardar claves en {file_path}: {e}")
            return False

    def _initialize_service_state(self):
        """Inicializa el estado del servicio (xPub, listas de claves)."""
        self.master_xpub = self._load_master_xpub()
        if not self.master_xpub:
            self.logger.info(f"No se encontró xPub. Generando una nueva.")
            self.master_xpub = self._generate_and_save_master_xpub()

        self.valid_keys = self._load_keys_from_file(self.valid_keys_file)
        self.used_keys = self._load_keys_from_file(self.used_keys_file)

        if not self.valid_keys and self.master_xpub:
            self.logger.info(f"Lista de claves válidas vacía. Generando {self.initial_key_batch_size} claves.")
            start_idx = len(self.used_keys) if self.used_keys else 0
            new_keys = self.generate_one_time_keys(
                start_index=start_idx, 
                count=self.initial_key_batch_size,
                change_level_bip44=Bip44Changes.CHAIN_EXT
            )
            if new_keys: 
                self.valid_keys.extend(new_keys)
                self._save_keys_to_file(self.valid_keys, self.valid_keys_file)
                self.logger.info(f"{len(new_keys)} claves generadas y añadidas a {self.valid_keys_file}")
        
        self.logger.info("Servicio de claves inicializado.")
        self.logger.info(f"xPub Maestra: {self.master_xpub[:20]}...") 
        self.logger.info(f"Claves válidas cargadas: {len(self.valid_keys)}")
        self.logger.info(f"Claves usadas cargadas: {len(self.used_keys)}")


    def generate_one_time_keys(self, start_index: int, count: int, change_level_bip44: Bip44Changes) -> List[str]:
        """Genera un lote de direcciones P2PKH de un solo uso desde la xPub de la cuenta (m/44'/1'/account')."""
        if not self.master_xpub:
            self.logger.error("No se puede generar claves sin xPub maestra (de cuenta).")
            return []
        keys = []
        try:
            xpub_account_obj = Bip44.FromExtendedKey(self.master_xpub, Bip44Coins.BITCOIN_TESTNET)
            change_node = xpub_account_obj.Change(change_level_bip44)
            
            for i in range(count):
                key_idx = start_index + i
                address_node = change_node.AddressIndex(key_idx)
                address = address_node.PublicKey().ToAddress()
                keys.append(address)
            self.logger.info(f"Generadas {len(keys)} direcciones P2PKH desde la cadena {change_level_bip44.name} (m/44'/1'/{self.default_account_index}'/{int(change_level_bip44)}).")
        except Exception as e:
            self.logger.error(f"Error generando claves desde xPub: {e}", exc_info=True)
        return keys

    def _derive_and_check_key(self, change_level: Bip44Changes, key_index: int, key_to_validate: str) -> bool:
        """Auxiliar para derivar y comparar una clave P2PKH desde la xPub de la cuenta (m/44'/1'/account')."""
        if not self.master_xpub: return False
        try:
            xpub_account_obj = Bip44.FromExtendedKey(self.master_xpub, Bip44Coins.BITCOIN_TESTNET)
            change_node = xpub_account_obj.Change(change_level)
            address_node = change_node.AddressIndex(key_index)
            derived_address = address_node.PublicKey().ToAddress()
            return derived_address == key_to_validate
        except Exception:
            return False

    def validate_key_cryptographically(self, key_to_validate: str) -> bool:
        """Valida criptográficamente una clave."""
        if not self.master_xpub: return False
        
        for i in range(min(self.crypto_validation_window_size, self.max_index_to_check_crypto)):
            if self._derive_and_check_key(Bip44Changes.CHAIN_EXT, i, key_to_validate):
                self.logger.info(f"Clave {key_to_validate} validada cripto (externa, índice {i}).")
                return True
            
        for i in range(min(self.crypto_validation_window_size, self.max_index_to_check_crypto)):
            if self._derive_and_check_key(Bip44Changes.CHAIN_INT, i, key_to_validate):
                self.logger.info(f"Clave {key_to_validate} validada cripto (interna, índice {i}).")
                return True
        self.logger.debug(f"Clave {key_to_validate} no validada criptográficamente.")
        return False

    def mark_key_as_used(self, key: str) -> bool:
        """Marca una clave como usada y persiste los cambios."""
        key_was_in_valid = False
        if key in self.valid_keys:
            try:
                self.valid_keys.remove(key)
                key_was_in_valid = True
            except ValueError: pass

        if key not in self.used_keys:
            self.used_keys.append(key)
        
        saved_used = self._save_keys_to_file(self.used_keys, self.used_keys_file)
        saved_valid = True
        if key_was_in_valid:
             saved_valid = self._save_keys_to_file(self.valid_keys, self.valid_keys_file)

        if saved_used and saved_valid:
            self.logger.info(f"Clave {key} marcada como usada. Válidas restantes: {len(self.valid_keys)}, Usadas: {len(self.used_keys)}")
            return True
        else:
            self.logger.error(f"Error al persistir cambios al marcar clave {key} como usada.")
            return False

    def handle_service_request(self, received_key: str) -> Tuple[str, int]:
        """Procesa la solicitud de servicio validando la clave."""
        if not self.master_xpub: 
            self.logger.critical("xPub maestra no está disponible. No se pueden procesar solicitudes.")
            return "Error crítico del servidor: xPub no disponible.", 503 

        if not received_key:
            return "Clave no proporcionada.", 400

        if received_key in self.used_keys:
            self.logger.warning(f"Intento de uso de clave ya utilizada: {received_key}")
            return "Clave inválida (ya usada).", 403

        if received_key in self.valid_keys:
            if self.mark_key_as_used(received_key):
                self.logger.info(f"Clave {received_key} válida y procesada (de lista).")
                return "Clave válida, marcada como usada.", 200
            else:
                return "Error interno del servidor al marcar clave.", 500
        
        if self.validate_key_cryptographically(received_key):
            if self.mark_key_as_used(received_key):
                self.logger.info(f"Clave {received_key} válida y procesada (cripto).")
                return "Clave válida (verificada criptográficamente), marcada como usada.", 200
            else:
                return "Error interno del servidor al marcar clave (cripto).", 500

        self.logger.warning(f"Clave inválida o no reconocida: {received_key}")
        return "Clave inválida (no reconocida).", 403



app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

key_serv = KeyService(app_config=config)


@app.route('/handle_request', methods=['POST'])
def handle_request_endpoint():
    """Endpoint Flask para manejar solicitudes de servicio."""
    if not request.is_json:
        return jsonify({"error": "Se esperaba Content-Type application/json."}), 415
    
    data = request.get_json()
    if data is None:
        return jsonify({"error": "Cuerpo JSON inválido o vacío."}), 400

    received_key = data.get("key")
    if not received_key: 
         return jsonify({"error": "Atributo 'key' no encontrado en JSON."}), 400

    try:
        response_message, status_code = key_serv.handle_service_request(received_key)
        return jsonify({"message": response_message}), status_code
    except Exception as e:
        key_serv.logger.error(f"Error inesperado en endpoint /handle_request: {e}", exc_info=True)
        return jsonify({"error": "Error interno del servidor.", "detail": str(e)}), 500


if __name__ == '__main__':
    key_serv.logger.info(f"Iniciando servidor Flask en host 0.0.0.0 puerto {config.get('flask', 'port', fallback=5000)}")
    app.run(
        host=config.get("flask", "host", fallback='0.0.0.0'),
        port=config.getint("flask", "port", fallback=5000),
        debug=config.getboolean("flask", "debug", fallback=False)
    )