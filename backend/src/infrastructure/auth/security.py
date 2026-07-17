"""Hashing e verificação de senha (bcrypt via passlib).

`get_password_hash` é usado por qualquer criação de usuário que parta de uma
senha em texto plano (change `user-management`; o bootstrap do primeiro admin
em `schema.py` recebe o hash já pronto via `ADMIN_PASSWORD_HASH`, gerado fora
do processo). `verify_password` é usado no login (`task-rest-1`) para
comparar a senha informada com o hash em tempo constante. Decisão de design:
sessão server-side, não JWT — nenhuma dependência de `python-jose`/`pyjwt` é
adicionada aqui.
"""

from __future__ import annotations

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Gera o hash bcrypt de uma senha em texto plano."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Compara, em tempo constante, uma senha em texto plano com um hash bcrypt."""
    return _pwd_context.verify(plain_password, password_hash)
