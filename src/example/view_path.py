import re
import matplotlib.pyplot as plt

# >>> Hier den Agent-Output einkopieren <<<
output = """
[Point(x=0.0, y=0.0), Point(x=0.0, y=5.0), Point(x=1.0, y=5.0), Point(x=1.0, y=0.0), Point(x=2.0, y=0.0), Point(x=2.0, y=5.0), Point(x=3.0, y=5.0), Point(x=3.0, y=0.0), Point(x=4.0, y=0.0)]
"""

points = [
    (float(x), float(y))
    for x, y in re.findall(r"Point\(x=([-\d.]+),\s*y=([-\d.]+)\)", output)
]

x_vals = [p[0] for p in points]
y_vals = [p[1] for p in points]

fig, ax = plt.subplots(figsize=(6, 8))
ax.plot(x_vals, y_vals, marker="o")

for idx, (x, y) in enumerate(zip(x_vals, y_vals), start=1):
    ax.text(x + 0.05, y + 0.05, str(idx), fontsize=8)

ax.set_xlim(min(x_vals) - 1, max(x_vals) + 1)
ax.set_ylim(min(y_vals) - 1, max(y_vals) + 1)
ax.set_title("Roboterpfad")
ax.set_xlabel("X")
ax.set_ylabel("Y")
ax.grid(True)
ax.axis("equal")

plt.tight_layout()
plt.show()
