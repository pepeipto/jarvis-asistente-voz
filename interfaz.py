"""
Interfaz visual de JARVIS: un orbe estilo HUD que late con la voz.

Usa tkinter, que ya viene con Python en Windows (no hay que instalar nada).
Estados: inactivo (en linea), escuchando, pensando, hablando, error.
"""
import math
import queue
import random
import time
import tkinter as tk

BG = (2, 6, 12)

# estado: (color principal, color brillante, etiqueta)
PALETA = {
    "inactivo":   ((0, 184, 217), (140, 235, 255), "E N   L Í N E A"),
    "escuchando": ((0, 229, 160), (170, 255, 220), "E S C U C H A N D O"),
    "pensando":   ((255, 176, 32), (255, 228, 160), "P R O C E S A N D O"),
    "hablando":   ((0, 212, 255), (235, 251, 255), "H A B L A N D O"),
    "error":      ((255, 77, 94), (255, 190, 195), "S I N   A U D I O"),
}
VELOCIDAD = {"inactivo": 1.0, "escuchando": 1.8, "pensando": 4.5, "hablando": 2.4, "error": 0.4}
PLACEHOLDER = "Escribe aquí tu mensaje y pulsa Enter…"
FUENTE = "Consolas"


def _mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _hex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c)


class Orbe:
    N_BARRAS = 72
    N_TICKS = 120

    def __init__(self, titulo="J.A.R.V.I.S."):
        try:  # nitidez en pantallas de alta resolucion (Windows)
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root = tk.Tk()
        self.root.title(titulo)
        self.root.configure(bg=_hex(BG))
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        try:
            self.esc = max(1.0, float(self.root.tk.call("tk", "scaling")) / 1.3333)
        except Exception:
            self.esc = 1.0
        alto = int(min(sh * 0.80, 980 * self.esc))
        ancho = int(alto * 0.88)
        self.root.geometry(f"{ancho}x{alto}+{(sw - ancho) // 2}+{max(0, (sh - alto) // 3)}")
        self.root.minsize(int(420 * self.esc), int(520 * self.esc))

        # barra de escritura (abajo)
        marco = tk.Frame(self.root, bg=_hex(BG))
        marco.pack(side="bottom", fill="x", padx=28, pady=(0, 20))
        self.entrada = tk.Entry(
            marco, bg="#06121c", fg="#2f7f90", insertbackground="#7be9ff", relief="flat",
            font=(FUENTE, 12), highlightthickness=1, highlightbackground="#0b3a4a",
            highlightcolor="#00b8d9",
        )
        self.entrada.pack(fill="x", ipady=9)
        self.entrada.insert(0, PLACEHOLDER)
        self.entrada.bind("<FocusIn>", self._foco)
        self.entrada.bind("<Return>", self._enviar)

        self.canvas = tk.Canvas(self.root, bg=_hex(BG), highlightthickness=0)
        self.canvas.pack(side="top", fill="both", expand=True)

        self.root.bind("<F11>", lambda e: self.root.attributes(
            "-fullscreen", not self.root.attributes("-fullscreen")))
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))
        self.root.protocol("WM_DELETE_WINDOW", self._cerrar)

        # estado compartido (los hilos de trabajo solo escriben estos campos)
        self.estado_actual = "inactivo"
        self._obj = 0.0           # nivel de audio objetivo (0..1)
        self._nivel = 0.0         # nivel suavizado
        self._sim_hasta = 0.0     # si no hay audio real, simula latido hasta este instante
        self.mensajes = []        # [(rol, texto)]
        self.cola_texto = queue.Queue()
        self.color = list(PALETA["inactivo"][0])
        self.brillo = list(PALETA["inactivo"][1])
        self.barras = [0.0] * self.N_BARRAS
        self.semillas = [random.uniform(0, 6.283) for _ in range(self.N_BARRAS)]
        self.ang = [0.0, 0.0, 0.0, 0.0]
        self.t0 = self._t_prev = time.time()
        self._cerrado = False
        self._cierre_pedido = False

    # ------------------------------------------------------------ API para otros hilos
    def set_estado(self, nombre):
        self.estado_actual = nombre if nombre in PALETA else "inactivo"

    def set_nivel(self, x):
        self._obj = max(self._obj * 0.6, max(0.0, min(1.0, float(x))))

    def simular(self, segundos):
        self._sim_hasta = time.time() + segundos

    def log(self, rol, texto):
        self.mensajes.append((rol, texto))
        del self.mensajes[:-6]

    def editar_ultimo(self, rol, texto):
        for i in range(len(self.mensajes) - 1, -1, -1):
            if self.mensajes[i][0] == rol:
                self.mensajes[i] = (rol, texto)
                return

    def cerrar(self):
        self._cierre_pedido = True

    def run(self):
        self._tick()
        self.root.mainloop()

    # ------------------------------------------------------------ eventos
    def _foco(self, _=None):
        if self.entrada.get() == PLACEHOLDER:
            self.entrada.delete(0, "end")
            self.entrada.config(fg="#7be9ff")

    def _enviar(self, _=None):
        txt = self.entrada.get().strip()
        if not txt or txt == PLACEHOLDER:
            return
        self.entrada.delete(0, "end")
        self.cola_texto.put(txt)

    def _cerrar(self):
        self._cerrado = True
        self.root.destroy()

    # ------------------------------------------------------------ dibujo
    def _tick(self):
        if self._cerrado:
            return
        if self._cierre_pedido:
            self._cerrar()
            return
        try:
            self._dibujar()
        except tk.TclError:
            return
        except Exception as e:  # nunca romper la animacion por un fallo de dibujo
            print("[UI]", e)
        self.root.after(33, self._tick)

    def _dibujar(self):
        c = self.canvas
        w = max(c.winfo_width(), 300)
        h = max(c.winfo_height(), 300)
        ahora = time.time()
        t = ahora - self.t0
        dt = min(0.1, ahora - self._t_prev)
        self._t_prev = ahora
        est = self.estado_actual
        pal_main, pal_hi, etiqueta = PALETA.get(est, PALETA["inactivo"])

        for i in range(3):  # transicion suave de color
            self.color[i] += (pal_main[i] - self.color[i]) * 0.10
            self.brillo[i] += (pal_hi[i] - self.brillo[i]) * 0.10

        obj = self._obj
        if ahora < self._sim_hasta:
            obj = max(obj, 0.30 + 0.30 * abs(math.sin(t * 7.3)) * (0.6 + 0.4 * math.sin(t * 2.1)))
        self._nivel += (obj - self._nivel) * (0.55 if obj > self._nivel else 0.10)
        self._obj *= 0.85
        nivel = self._nivel

        vel = VELOCIDAD.get(est, 1.0) * (1 + nivel)
        self.ang[0] += dt * 0.10 * vel
        self.ang[1] += dt * 0.55 * vel
        self.ang[2] -= dt * 0.80 * vel
        self.ang[3] += dt * 1.40 * vel

        c.delete("d")
        pie = int(210 * self.esc)                  # espacio inferior para estado y subtitulos
        alto_orbe = h - pie
        cx = w / 2
        cy = 30 + alto_orbe / 2
        R = max(70.0, min(w * 0.46, alto_orbe * 0.5 - 6))

        def col(a):
            return _hex(_mix(BG, self.color, a))

        def hi(a):
            return _hex(_mix(BG, self.brillo, a))

        def circ(r, outline="", width=1, fill=""):
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=outline, width=width,
                          fill=fill, tags="d")

        def arco(r, ini, ext, color, width):
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=ini, extent=ext, style="arc",
                         outline=color, width=width, tags="d")

        # resplandor de fondo
        for k in range(8, 0, -1):
            circ(R * (0.30 + k * 0.045 + nivel * 0.05), fill=col(0.012 * (9 - k) + 0.02 * nivel))

        # anillos tenues
        circ(R * 0.98, outline=col(0.20))
        circ(R * 0.60, outline=col(0.12))
        circ(R * 0.36, outline=col(0.18))

        # marcas giratorias exteriores
        for i in range(self.N_TICKS):
            a = self.ang[0] + i * 2 * math.pi / self.N_TICKS
            largo = i % 10 == 0
            r0, r1 = R * (0.90 if largo else 0.93), R * (0.99 if largo else 0.96)
            ca, sa = math.cos(a), math.sin(a)
            c.create_line(cx + ca * r0, cy + sa * r0, cx + ca * r1, cy + sa * r1,
                          fill=hi(0.70) if largo else col(0.35), width=2 if largo else 1, tags="d")

        # arcos giratorios
        brillo_arco = 0.55 + 0.45 * nivel
        g1 = math.degrees(self.ang[1])
        g2 = math.degrees(self.ang[2])
        for k in range(3):
            arco(R * 0.85, g1 + k * 120, 70, col(brillo_arco), 4)
        for k in range(2):
            arco(R * 0.77, g2 + k * 180, 110, hi(0.55 + 0.4 * nivel), 2)
        for k in range(8):
            arco(R * 0.69, g1 * 0.7 + k * 45, 22, col(0.55), 1)

        # barras radiales (el "ecualizador" circular)
        r0 = R * 0.44
        largo_max = R * 0.21
        ancho = 3 if R > 140 else 2
        for i in range(self.N_BARRAS):
            a = i * 2 * math.pi / self.N_BARRAS - math.pi / 2
            if est == "pensando":                # barrido tipo radar
                d = (a - self.ang[3]) % (2 * math.pi)
                d = min(d, 2 * math.pi - d)
                v = 0.08 + 0.9 * max(0.0, 1 - d / 1.0) ** 2
            else:
                ruido = 0.5 + 0.5 * math.sin(t * (3 + i % 5) + self.semillas[i])
                respiro = 0.05 * (1 + math.sin(t * 1.5 + i * 0.25))
                v = 0.05 + respiro + nivel * (0.30 + 0.70 * ruido)
            self.barras[i] += (v - self.barras[i]) * 0.45
            b = max(0.0, min(1.0, self.barras[i]))
            ca, sa = math.cos(a), math.sin(a)
            r1 = r0 + 3 + largo_max * b
            color = _hex(_mix(_mix(BG, self.color, 0.55), self.brillo, b))
            c.create_line(cx + ca * r0, cy + sa * r0, cx + ca * r1, cy + sa * r1,
                          fill=color, width=ancho, capstyle="round", tags="d")

        # nucleo
        rc = R * 0.30 * (1 + 0.14 * nivel)
        circ(rc * 1.18, fill=col(0.10 + 0.15 * nivel))
        circ(rc, fill=col(0.40 + 0.35 * nivel), outline=hi(0.9), width=2)
        circ(rc * 0.62, fill=_hex(_mix(self.color, self.brillo, 0.35 + 0.5 * nivel)))
        circ(rc * 0.24, fill=hi(1.0))
        arco(rc * 1.38, math.degrees(self.ang[1]) * 1.3, 95, hi(0.85), 2)
        arco(rc * 1.38, math.degrees(self.ang[1]) * 1.3 + 180, 95, hi(0.85), 2)

        # marco HUD en las esquinas
        m, L = 16, 28
        for sx, x in ((1, m), (-1, w - m)):
            for sy, y in ((1, m), (-1, h - pie + 60)):
                c.create_line(x, y, x + sx * L, y, fill=col(0.55), width=2, tags="d")
                c.create_line(x, y, x, y + sy * L, fill=col(0.55), width=2, tags="d")
        c.create_text(m + 8, m + 38, text="J.A.R.V.I.S.", anchor="w",
                      font=(FUENTE, 11, "bold"), fill=hi(0.75), tags="d")
        c.create_text(w - m - 8, m + 38, text=time.strftime("%H:%M:%S"), anchor="e",
                      font=(FUENTE, 11), fill=col(0.75), tags="d")

        # estado y subtitulos
        y = cy + R + 30
        c.create_text(cx, y, text=etiqueta, font=(FUENTE, 15, "bold"), fill=hi(0.95), tags="d")
        y += 30
        ancho_txt = max(200, w - 100)
        for rol, texto in self.mensajes[-2:]:
            texto = texto if len(texto) < 180 else texto[:177] + "…"
            if rol == "tu":
                txt, color = "TÚ  ›  " + texto, col(0.65)
            elif rol == "sistema":
                txt, color = "·  " + texto, _hex(_mix(BG, (255, 176, 32), 0.7))
            else:
                txt, color = "JARVIS  ›  " + texto, hi(0.95)
            it = c.create_text(cx, y, text=txt, width=ancho_txt, justify="center", anchor="n",
                               font=(FUENTE, 11), fill=color, tags="d")
            bb = c.bbox(it)
            y = (bb[3] if bb else y + 20) + 8
