from __future__ import annotations

import msgspec

class Task0(msgspec.Struct, frozen=True):
    """
    x und y Koordinaten des Suchgebiets
    """
    searcharea : str

class Task1(msgspec.Struct, frozen=True):
    """
    Erstellte Pfadpunkte
    """
    waypoints : str

class Task2(msgspec.Struct, frozen=True):
    """
    Weg ablaufen, dabei Bilder aufnehmen und an die KI schicken, um Müll zu erkennen. KI schickt zurück, ob Müll erkannt wurde und wo er sich befindet.
    """
    task21 : Task2_walk
    task22 : Task2_litter

class Task2_walk(msgspec.Struct, frozen=True):
    """
    Letzter Wegpunkt
    """
    lastwaypoint : str

class Task2_litter(msgspec.Struct, frozen=True):
    """
    Müllerkennung und Validierung per Kamera
    """
    frame: str 
    detection: str 
    overlay: str 
    validtrashpoint: str

class Task3(msgspec.Struct, frozen=True):
    """
    Letzten Wegpunkt erreicht, müll gescannt
    """
    lastwaypoint : str
    

class Task4(msgspec.Struct, frozen=True):
    """
    Erstellte Müllpunkte
    """
    trashpoints : str

class Task5(msgspec.Struct, frozen=True):
    """
    Läuft zu Müllpunkten
    """
    

class Task6(msgspec.Struct, frozen=True):
    """
    Gibt Meldung wenn letzten Müllpunkt erreicht
    """
    lasttrashpoints : str

class demo(msgspec.Struct, frozen=True):
    test : str


class Topics(msgspec.Struct, frozen=True):
    task0: Task0
    task1: Task1
    task2: Task2
    task3: Task3
    task4: Task4
    task5: Task5
    task6: Task6
    demo: demo



TOPICS = Topics(
    task0=Task0(searcharea="task0/searcharea"),
    task1=Task1(waypoints="task1/waypoints"),
    task2=Task2(task21=Task2_walk(lastwaypoint="task2/task21/lastwaypoint"), task22=Task2_walk(frame="task2/task22/frame", detection="task2/task22/detection", overlay="task2/task22/overlay")),
    task3=Task3(waypoints="task3/lastwaypoint"),
    task4=Task4(waypoints="task4/trashpoints"),
    task5=Task5(waypoints="task5/"),
    task6=Task6(waypoints="task6/lasttrashpoints"),
    demo=demo(test="demo/test"),
)