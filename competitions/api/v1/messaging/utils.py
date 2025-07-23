import asyncio
from competitions.api.v1.messaging.publishers import publish_audit_log 

def run_async_audit(log_payload: dict):
    try:
        asyncio.run(publish_audit_log(log_payload))
    except Exception as e:
        print(f"CRITICAL: Falha ao publicar log de auditoria!")