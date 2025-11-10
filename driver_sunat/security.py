# -*- coding: utf-8 -*-
from cryptography.fernet import Fernet

def encrypt_password(password: str, key: bytes) -> bytes:
    """Cifra una contraseña en texto plano usando la clave proporcionada."""
    f = Fernet(key)
    return f.encrypt(password.encode('utf-8'))

def decrypt_password(encrypted_password: bytes, key: bytes) -> str:
    """Descifra una contraseña cifrada usando la clave proporcionada."""
    f = Fernet(key)
    return f.decrypt(encrypted_password).decode('utf-8')
