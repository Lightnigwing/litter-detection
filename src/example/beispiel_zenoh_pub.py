import zenoh
import time
from topics.topics import TOPICS
from config import Settings

# Zenoh-Session starten
settings = Settings()
conf = zenoh.Config()
conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
session = zenoh.open(conf)

topic = TOPICS.demo.test

i = 0
for i in range(10):
    msg = f"Hallo {i}"
    session.put(topic, msg)
    print(f"Gesendet: {msg}")
    
    time.sleep(1)  # jede Sekunde senden