import aio_pika
import json
import os

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