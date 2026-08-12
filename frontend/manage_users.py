"""
Gestión manual de usuarios de Academic Pregrader.

Uso (local o dentro del contenedor con `az containerapp exec`):

    python manage_users.py add <usuario> [--admin]   # pide la contraseña
    python manage_users.py passwd <usuario>          # cambia la contraseña
    python manage_users.py del <usuario>
    python manage_users.py list

La base de datos vive en PREGRADER_CONFIG_DIR/users.db (persistido en Azure Files).
"""

import getpass
import sys

import auth


def _prompt_password() -> str:
    pwd = getpass.getpass("Contraseña: ")
    if pwd != getpass.getpass("Repite la contraseña: "):
        sys.exit("Las contraseñas no coinciden.")
    if len(pwd) < 8:
        sys.exit("La contraseña debe tener al menos 8 caracteres.")
    return pwd


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    cmd = sys.argv[1].lower()

    if cmd == "list":
        users = auth.list_users()
        print("\n".join(users) if users else "(sin usuarios)")

    elif cmd == "add":
        if len(sys.argv) < 3:
            sys.exit("Uso: python manage_users.py add <usuario> [--admin]")
        username = sys.argv[2]
        is_admin = "--admin" in sys.argv[3:]
        try:
            auth.create_user(username, _prompt_password(), is_admin=is_admin)
        except Exception as exc:  # username duplicado, etc.
            sys.exit(f"No se pudo crear el usuario: {exc}")
        rol = " (admin)" if is_admin else ""
        print(f"Usuario '{username.strip().lower()}'{rol} creado.")

    elif cmd == "passwd":
        if len(sys.argv) < 3:
            sys.exit("Uso: python manage_users.py passwd <usuario>")
        username = sys.argv[2]
        if auth.set_password(username, _prompt_password()):
            print(f"Contraseña actualizada para '{username.strip().lower()}'.")
        else:
            sys.exit("Usuario no encontrado.")

    elif cmd in ("del", "delete", "rm"):
        if len(sys.argv) < 3:
            sys.exit("Uso: python manage_users.py del <usuario>")
        username = sys.argv[2]
        if auth.delete_user(username):
            print(f"Usuario '{username.strip().lower()}' eliminado.")
        else:
            sys.exit("Usuario no encontrado.")

    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
