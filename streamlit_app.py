import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Análisis de sesiones", layout="wide")
st.title("Análisis de estabilidad postural")

# ---------- Inicio de sesión (cada visitante tiene su propia sesión) ----------
if "sb" not in st.session_state:
    with st.form("login"):
        email = st.text_input("Email")
        pwd = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar"):
            try:
                sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])
                sb.auth.sign_in_with_password({"email": email, "password": pwd})
                st.session_state.sb = sb
                st.rerun()
            except Exception:
                st.error("No se pudo iniciar sesión.")
    st.stop()

sb = st.session_state.sb
filas = (
    sb.table("sesiones").select("id,created_at,datos")
    .order("created_at", desc=True).limit(200).execute().data
)
if not filas:
    st.info("Todavía no hay sesiones guardadas.")
    st.stop()


def nombre(f):
    return f"{f['created_at'][:16].replace('T', ' ')} · {f['datos'].get('etiqueta') or 'sin código'}"


sel = st.selectbox("Sesión", filas, format_func=nombre)
d = sel["datos"]
n = int(d["n_marcadores"])
M = np.array(d["muestras"], dtype=float)      # una fila por disparo: [t, x1, y1, d1, x2, y2, d2, ...]
t = M[:, 0]
picos = d.get("picos_db", [])
n_tiros = len(M)

c1, c2 = st.columns(2)
diam_mm = c1.number_input("Diámetro real del marcador (mm)", value=float(d.get("diametro_mm") or 20.0))
c2.metric("Disparos (una foto por disparo)", n_tiros)
st.caption(f"Umbral de volumen: {d.get('umbral_db', '—')} dB · disparos oídos sin ver todos los marcadores: "
           f"{d.get('disparos_sin_marcadores', 0)}")

# ---------- Conversión a mm con el diámetro del marcador como referencia ----------
series = {}
for i in range(n):
    x, y, dd = M[:, 1 + 3 * i], M[:, 2 + 3 * i], M[:, 3 + 3 * i]
    mm_px = diam_mm / np.median(dd)
    series[i + 1] = {"ap": x * mm_px, "vert": -y * mm_px}   # vertical positivo hacia arriba

# ---------- Tabla con las coordenadas de cada disparo ----------
tabla = pd.DataFrame({"Disparo": np.arange(1, n_tiros + 1), "t (s)": np.round(t, 2)})
if len(picos) == n_tiros:
    tabla["Pico (dB)"] = picos
for m, s in series.items():
    tabla[f"M{m} X (mm)"] = np.round(s["ap"], 2)
    tabla[f"M{m} Y (mm)"] = np.round(s["vert"], 2)

st.subheader("Coordenadas por disparo")
st.dataframe(tabla, use_container_width=True)

# ---------- Variación entre disparos ----------
res = []
if n_tiros >= 3:
    idx = np.arange(1, n_tiros + 1)
    for m, s in series.items():
        for eje, nom in (("vert", "Vertical"), ("ap", "Anteroposterior")):
            v = s[eje]
            res.append({
                "Marcador": m, "Eje": nom,
                "Media (mm)": round(float(v.mean()), 2),
                "Desv. típica (mm)": round(float(np.std(v, ddof=1)), 2),
                "Rango (mm)": round(float(v.max() - v.min()), 2),
                "Tendencia (mm/disparo)": round(float(np.polyfit(idx, v, 1)[0]), 3),
            })
    st.subheader("Variación entre disparos")
    st.dataframe(pd.DataFrame(res), use_container_width=True)
else:
    st.warning("Hacen falta al menos 3 disparos para calcular la variación y la tendencia.")

# ---------- Gráficos ----------
fig, ax = plt.subplots(1, 3, figsize=(15, 4))
for m, s in series.items():
    ax[0].plot(s["ap"], s["vert"], marker="o", label=f"Marcador {m}")          # unidos en orden cronológico
    for k in range(n_tiros):
        ax[0].annotate(str(k + 1), (s["ap"][k], s["vert"][k]), textcoords="offset points", xytext=(3, 3), fontsize=7)
    ax[1].plot(t, s["ap"] - s["ap"].mean(), marker="o", label=f"Marcador {m}")      # distancia a la media
    ax[2].plot(t, s["vert"] - s["vert"].mean(), marker="o", label=f"Marcador {m}")  # + = arriba
ax[0].set_title("Posición en cada disparo (orden cronológico)")
ax[0].set_xlabel("X (mm)")
ax[0].set_ylabel("Y (mm, + = arriba)")
ax[1].set_title("Desplazamiento en X respecto a la media")
ax[2].set_title("Desplazamiento en Y respecto a la media")
for a in ax[1:]:
    a.axhline(0, color="k", linestyle="--", linewidth=1)
    a.set_xlabel("Tiempo desde el inicio (s)")
    a.set_ylabel("mm (0 = media)")
for a in ax:
    a.legend()
fig.tight_layout()
st.pyplot(fig)

st.download_button("Descargar coordenadas (CSV)", tabla.to_csv(index=False).encode("utf-8"),
                   file_name="coordenadas_por_disparo.csv", mime="text/csv")
