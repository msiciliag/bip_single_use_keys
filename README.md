# Single Use Key for Remote services

This repository contains a simple implementation of a single-use key system for remote services. The keys are designed to be used once and then discarded, enhancing security by preventing reuse.
All keys are generated with a wallet address based on BIP-44, which allows for deterministic key generation. This means that the same key can be regenerated if needed, as long as the wallet address remains the same.

## Features
- **Single-use keys**: Each key can only be used once, preventing reuse and enhancing security.
- **Deterministic key generation**: Keys are generated based on a wallet address, allowing for regeneration if needed.
- **BIP-44 compliant**: The keys follow the BIP-44 standard for hierarchical deterministic wallets, ensuring compatibility with various wallet software.
- **Easy integration**: The system can be easily integrated into existing applications and services.
- **All code is highly modular**: The code is structured in a modular way, making it easy to understand and extend.
- **All code is written in Python**: The implementation is done in Python, making it accessible and easy to modify.
- **All code is well documented**: The code is thoroughly documented, providing clear explanations of the functionality and usage of each component.
- **All code is highly reusable**: The modular design allows for easy reuse of components in other projects or applications.

## Project Structure
- `client.py`: Contains the client-side implementation for generating and using single-use keys.
- `server.py`: Contains the server-side implementation for managing and validating single-use keys. Based on Flask, it provides an endpoint to make a request for a mockup service. This service will get a key from the user request and check if it is valid or not. For pointint out the validity of the key it will search for the key in the `/keys/valid.json` file. If the key is valid, it will mark it as used and move it to the `/keys/used.json` file. If the key was not in the `/keys/valid.json` file, it will try to check if it is in the `/keys/used.json` file, and if it is, it will return "Invalid key". If it was not in either file, it will check cryptographically if the key is valid or not based on the wallet address it possesses and the BIP-48 standard.
- `README.md`: This file, providing an overview of the project and its features.
- `/keys`: Directory containing the generated single-use keys.
    - `/keys/valid.json`: A JSON file containing valid single-use keys.
    - `/keys/used.json`: A JSON file containing used single-use keys.

## Usage
To use the single-use key system, follow these steps:
0. **Start the server**: Run the `server.py` script to start the server that manages the single-use keys.
1. **Generate a wallet address**: The `server.py` script generates a wallet address based on BIP-48. This address is used to generate the single-use keys. You can find the generated wallet address in the `server.py` script output or in the `/keys/valid.json` file.
2. **Generate a list of single-use keys**: The `server.py` script generates a list of single-use keys based on the wallet address.
3. **Get a key**: Use the `client.py` script to request a single-use key from the list saved on the directory `/keys/valid.json`.
4. **Use the key**: Use the single-use key for your remote service (in this case it is a simple Flask app that says "Valid key, marking as used" or "Invalid key").
5. **Mark the key as used**: After using the key, the `server.py` script will automatically mark the key as used and move it to the `/keys/used.json` file.

WARNING: The wallet uses the bitccoin testnet, so the keys generated are not valid for the mainnet. This is intended for testing purposes only.

## Requirements
To run this project, you need to have Python 3.x installed along with the following packages:
- `flask`: For the server-side implementation.
- `bip_utils`: For BIP-44 compliant key generation.
- `requests`: For making HTTP requests from the client to the server.