import zenoh
from src.topics import TOPICS
# Callback-Funktion für eingehende Daten
def listener(sample):
    print(f"Empfangen: {bytes(sample.payload)}")

from src.config import Settings# Zenoh-Session starten
settings = Settings()
conf = zenoh.Config()
conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
session = zenoh.open(conf)

key = TOPICS.demo.test

# Subscriber registrieren
sub = session.declare_subscriber(key, listener)

print("Warte auf Nachrichten...")

# Programm am Leben halten
input()