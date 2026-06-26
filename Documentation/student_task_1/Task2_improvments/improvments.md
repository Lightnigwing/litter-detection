# Verbesserungen des Vorschlages des Autoresearch

## Traningsdauer
Anstelle ein TIMELIMIT für einen Traningsrun zu setzen, sollte eine feste Anzahl an Epochen festgelegt werden die traniert wird, da verschiedene Hardware unterschiedlich lange braucht für eine Epoche und es mit einem TIMELIMIT nicht hardwareübergreifend vergleichbar wäre

## change varibales
Zu Anfang können mehrere Variablen verändert werden, solange man diese gut dokumentiert. Das ändern einzelner Variablen ist maximal für das finetuning nötig.

## OneCycleLR 
umgebaut auf timelimit, arbeitet jetzt mit total_steps, was es resistenter macht gegen earlystoppinbg

## Logging
Fertig:
- hardwarelogging
TODO:
- model mit pytorch loggen

## Validation 
Bei der for else Schleife das else entfernt, das die Validation immer geloggt wird 