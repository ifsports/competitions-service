#!/bin/sh
# /code/entrypoint.sh

set -e

DB_HOST=${POSTGRES_HOST:-db}
DB_PORT=${POSTGRES_PORT:-5432}

echo "Aguardando o banco de dados Postgres em ${DB_HOST}:${DB_PORT}..."

python << END
import socket
import time
import os
import sys

host = os.environ.get('POSTGRES_HOST', 'db')
port = int(os.environ.get('POSTGRES_PORT', '5432'))
timeout_seconds = 120  # Tempo máximo de espera em segundos (2 minutos)
start_time = time.time()

print(f"Tentando conectar ao banco de dados em {host}:{port}...")

while True:
    if time.time() - start_time > timeout_seconds:
        print(f"Timeout: O banco de dados em {host}:{port} não ficou disponível após {timeout_seconds} segundos.", file=sys.stderr)
        sys.exit(1)
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        print(f"O banco de dados em {host}:{port} está pronto.")
        break 
    except (socket.error, ConnectionRefusedError) as e:
        print(f"O banco de dados ainda não está pronto ({e}), tentando novamente em 5 segundos...")
        time.sleep(5)
END

echo "Aplicando migrações do banco de dados..."
python manage.py migrate --noinput

echo "Iniciando o servidor Gunicorn com o comando: $@"
exec "$@"