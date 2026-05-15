import json
import matplotlib.pyplot as plt

# Dein JSON-String
data_str = r'''
{"points":{"point1":{"x":0.0,"y":5.8},"point2":{"x":1.0,"y":5.8},"point3":{"x":1.0,"y":4.6},"point4":{"x":2.0,"y":4.6},"point5":{"x":2.0,"y":3.4},"point6":{"x":3.0,"y":3.4},"point7":{"x":3.0,"y":2.2},"point8":{"x":1.8,"y":2.2},"point9":{"x":1.8,"y":1.0},"point10":{"x":0.0,"y":1.0}}}
'''

# JSON parsen
data = json.loads(data_str)

# Punkte sortieren
points = data["points"]

sorted_points = sorted(
    points.items(),
    key=lambda item: int(item[0].replace("point", ""))
)

# X/Y extrahieren
x_vals = [p["x"] for _, p in sorted_points]
y_vals = [p["y"] for _, p in sorted_points]

# Plot
fig, ax = plt.subplots(figsize=(6, 8))

# Linien zeichnen
ax.plot(x_vals, y_vals, marker='o')

# Punktnummern anzeigen
for idx, (x, y) in enumerate(zip(x_vals, y_vals), start=1):
    ax.text(x, y, str(idx))

# Fenstergröße festlegen
ax.set_xlim(-1, max(x_vals) + 1)
ax.set_ylim(-1, max(y_vals) + 1)

ax.set_title("Roboterpfad")
ax.set_xlabel("X")
ax.set_ylabel("Y")
ax.grid(True)
ax.axis("equal")

plt.show()