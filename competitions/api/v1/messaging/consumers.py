import os
import django
import asyncio

DJANGO_SETTINGS_MODULE = os.getenv('DJANGO_SETTINGS_MODULE', 'competitions_service.settings')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', DJANGO_SETTINGS_MODULE)
print(f"INFO: [ConsumerSetup] Usando DJANGO_SETTINGS_MODULE: {DJANGO_SETTINGS_MODULE}")
try:
    django.setup()
    print("INFO: [ConsumerSetup] Django setup concluído com sucesso.")
except Exception as e:
    print(f"ERRO: [ConsumerSetup] Falha ao executar django.setup(): {e}")

import aio_pika
import json

from competitions.api.v1.services import update_team_from_request_in_db_django

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


REQUESTS_EVENTS_EXCHANGE = "requests_events_exchange"

COMPETITION_TEAM_CREATION_QUEUE = "competitions_service.queue.team_creation"
ROUTING_KEY_COMPETITION_TEAM_CREATION = "team.creation.update"


async def on_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        try:
            data = json.loads(message.body.decode())
            print(f" [requests_service] Received message: {data}")
            print(f" [requests_service] Routing Key: {message.routing_key}")

            if hasattr(asyncio, 'to_thread'):
                db_result = await asyncio.to_thread(update_team_from_request_in_db_django, data)
            else:
                loop = asyncio.get_event_loop()
                db_result = await loop.run_in_executor(None, update_team_from_request_in_db_django, data)

            print(f" [requests_service] Resultado do processamento do DB: {db_result}")

        except json.JSONDecodeError as e:
            print(f" [requests_service] Erro ao decodificar JSON: {e}. Mensagem será rejeitada.")
            raise
        except Exception as e:
            print(f" [requests_service] Erro inesperado ao processar mensagem ou DB: {e}")
            raise


async def main_consumer():
    retry_delay = 10
    while True:
        connection = None
        try:
            print(f"INFO: [requests_service] Consumidor: Tentando conectar ao RabbitMQ em {RABBITMQ_URL}...")
            connection = await aio_pika.connect_robust(RABBITMQ_URL, timeout=15)

            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=10)

                exchange = await channel.declare_exchange(
                    REQUESTS_EVENTS_EXCHANGE,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True
                )

                # Fila para criar equipe em competition
                team_creation_queue = await channel.declare_queue(
                    COMPETITION_TEAM_CREATION_QUEUE,
                    durable=True
                )

                await team_creation_queue.bind(exchange, routing_key=ROUTING_KEY_COMPETITION_TEAM_CREATION)

                print(f"INFO: [requests_service] Consumidor: Conectado! '{COMPETITION_TEAM_CREATION_QUEUE}' esperando por mensagens com routing key '{ROUTING_KEY_COMPETITION_TEAM_CREATION}'. Para sair pressione CTRL+C")

                await team_creation_queue.consume(on_message)


                await asyncio.Future()

        except aio_pika.exceptions.AMQPConnectionError as e:
            print(
                f"AVISO: [requests_service] Consumidor: Falha na conexão com RabbitMQ (AMQPConnectionError): {e}. Tentando novamente em {retry_delay} segundos...")
        except ConnectionRefusedError as e:
            print(
                f"AVISO: [requests_service] Consumidor: Conexão recusada (ConnectionRefusedError): {e}. Provavelmente o RabbitMQ não está totalmente pronto. Tentando novamente em {retry_delay} segundos...")
        except asyncio.CancelledError:
            print("INFO: [requests_service] Consumidor: Tarefa cancelada. Encerrando consumidor.")
            break
        except Exception as e:
            print(
                f"ERRO: [requests_service] Consumidor: Erro inesperado: {e}. Tentando novamente em {retry_delay} segundos...")
        finally:
            if connection and not connection.is_closed:
                print("INFO: [requests_service] Consumidor: Fechando conexão RabbitMQ no finally do loop.")
                await connection.close()

            current_task = asyncio.current_task()
            if current_task and current_task.cancelled():
                print(
                    "INFO: [competitions_service] Consumidor: Saindo do loop de reconexão devido ao cancelamento (detectado no finally).")
                break

        print(f"INFO: [competitions_service] Consumidor: Aguardando {retry_delay}s antes da próxima tentativa de conexão.")
        await asyncio.sleep(retry_delay)


if __name__ == "__main__":
    print("INFO: [ConsumerMain] Iniciando o loop principal do consumidor...")
    try:
        asyncio.run(main_consumer())
    except KeyboardInterrupt:
        print("INFO: [ConsumerMain] Consumidor encerrado manualmente (KeyboardInterrupt).")
    except Exception as e:
        print(f"ERRO: [ConsumerMain] Erro crítico no loop principal do consumidor: {e}")
    finally:
        print("INFO: [ConsumerMain] Loop principal do consumidor finalizado.")