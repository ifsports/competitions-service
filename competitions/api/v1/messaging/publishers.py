from ipaddress import ip_address

import aio_pika
import json
import os
import uuid
from datetime import datetime, timezone

RABBITMQ_USER_DEFAULT = "guest"
RABBITMQ_PASSWORD_DEFAULT = "guest"
RABBITMQ_HOST_DEFAULT = "rabbitmq"
RABBITMQ_PORT_DEFAULT = "5672"
RABBITMQ_VHOST_DEFAULT = "/"

RABBITMQ_URL = os.getenv("RABBITMQ_URL")

if not RABBITMQ_URL:
    user = os.getenv("RABBITMQ_USER", RABBITMQ_USER_DEFAULT)
    password = os.getenv("RABBITMQ_PASSWORD", RABBITMQ_PASSWORD_DEFAULT)
    host = os.getenv("RABBITMQ_HOST", RABBITMQ_HOST_DEFAULT)
    port = os.getenv("RABBITMQ_PORT", RABBITMQ_PORT_DEFAULT)
    vhost = os.getenv("RABBITMQ_VHOST", RABBITMQ_VHOST_DEFAULT)

    if not vhost or vhost == "/":
        vhost_path = ""
    elif not vhost.startswith("/"):
        vhost_path = "/" + vhost
    else:
        vhost_path = vhost

    RABBITMQ_URL = f"amqp://{user}:{password}@{host}:{port}{vhost_path}"
    print(f"INFO: RABBITMQ_URL não estava definida no ambiente. URL montada: {RABBITMQ_URL}")
else:
    print(f"INFO: Usando RABBITMQ_URL definida no ambiente: {RABBITMQ_URL}")


MATCHES_EXCHANGE = "matches_commands_exchange"

async def publish_match_created(match_data):
    """
    Publica uma mensagem no RabbitMQ quando uma partida é criada.
    :param match_data: Dados da partida a serem publicados.
    """
    connection = None
    try:
        # Conecta ao RabbitMQ usando a URL configurada
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()

            exchange = await channel.declare_exchange(
                MATCHES_EXCHANGE,
                aio_pika.ExchangeType.DIRECT,
                durable=True
            )

            message = aio_pika.Message(
                body=json.dumps(match_data).encode(),
                content_type="application/json"
            )

            routing_key = "match_created"

            await exchange.publish(message, routing_key=routing_key)
            print(f"[competitions_service] Sent '{routing_key}':'{match_data}'")
    except aio_pika.exceptions.AMQPConnectionError as e:
        print(f"Erro de conexão com RabbitMQ: {e}")
    except Exception as e:
        print(f"Erro ao publicar mensagem: {e}")
    finally:
            if connection and not connection.is_closed:
                await connection.close()
                print("Conexão com RabbitMQ fechada.")

def generate_log_payload(
    event_type: str,
    service_origin: str,
    entity_type,
    entity_id,
    operation_type: str,
    campus_code: str,
    user_registration: str,
    request_object,
    correlation_id: str | None = None,
    old_data: dict | None = None,
    new_data: dict | None = None,
) -> dict:
    """
    Gera um payload de log estruturado com old_data e new_data
    como objetos Python (prontos para serem serializados como JSON nativo).
    """
    x_forwarded_for = request_object.META.get('HTTP_X_FORWARDED_FOR')

    ip = "127.0.0.1"

    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request_object.META.get('REMOTE_ADDR')


    #if request_object.correlation_id:
    #    correlation_id = request_object.correlation_id
    #else:
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    return{
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "campus_code": campus_code,
        "user_id": user_registration,
        "service_origin": service_origin,
        "event_type": event_type,
        "operation_type": operation_type,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "old_data": old_data,
        "new_data": new_data,
        "ip_address": ip
    }

# --- Função de Publicação com Routing Key Dinâmica ---

AUDIT_EXCHANGE = "events_exchange"

async def publish_audit_log(log_payload: dict):
    """
    Publica uma mensagem de log de auditoria no RabbitMQ com uma routing key específica.

    :param log_payload: Dados de log a serem publicados.
    """
    connection = None
    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)

        async with connection:
            channel = await connection.channel()

            exchange = await channel.declare_exchange(
                AUDIT_EXCHANGE,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

             # 1. Montar o corpo no formato Celery: (args, kwargs, options)
            celery_body = (
                [log_payload],  # args: seu payload vai aqui
                {},             # kwargs: vazio neste caso
                {"callbacks": None, "errbacks": None, "chain": None, "chord": None},
            )

            # 2. Definir os cabeçalhos (headers) essenciais do Celery
            task_id = str(uuid.uuid4())
            celery_headers = {
                'lang': 'py',
                'task': 'process_audit_log', # O nome exato da sua tarefa
                'id': task_id,
                'root_id': task_id,
                'parent_id': None,
                'group': None,
            }

            # 3. Criar a mensagem aio_pika com todas as propriedades
            message = aio_pika.Message(
                body=json.dumps(celery_body).encode('utf-8'),
                headers=celery_headers,
                content_type='application/json',  # Celery usa JSON por padrão
                content_encoding='utf-8',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            routing_key = f'{log_payload["event_type"]}'

            # A routing_key agora é o parâmetro recebido pela função
            await exchange.publish(message, routing_key=routing_key)

            print(f"[audit_service] Log enviado para exchange '{AUDIT_EXCHANGE}' com routing key '{routing_key}'")
            print(f"[audit_service] Log payload: {log_payload}")

    except aio_pika.exceptions.AMQPConnectionError as e:
        print(f"Erro de conexão com RabbitMQ: {e}")
    except Exception as e:
        print(f"Erro ao publicar mensagem de auditoria: {e}")
