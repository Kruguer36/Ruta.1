import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime
import math
import io
import json
import requests
import urllib.parse

# ==========================================
# 1. CONFIGURACIÓN INICIAL DE LA APP
# ==========================================
st.set_page_config(
    page_title="Gestión de Rutas de Recolección - Envigado",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)

ENVIGADO_LAT = 6.17591
ENVIGADO_LON = -75.59174

# ==========================================
# 2. FUNCIONES DE APOYO (GEOCERCAS, BUSCADOR Y OSRM)
# ==========================================
def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    """Calcula la distancia Haversine en metros entre dos coordenadas."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def normalizar_texto(texto):
    """Normaliza abreviaturas comunes en direcciones colombianas."""
    reemplazos = {"cra": "Carrera", "cll": "Calle", "tv": "Transversal", "dg": "Diagonal", "cq": "Circular"}
    palabras = [reemplazos.get(p.lower().replace(".", ""), p) for p in texto.split()]
    return " ".join(palabras)

def buscar_lugar_nominatim(query):
    """Busca lugares en el Valle de Aburrá usando la API de Nominatim."""
    texto_limpio = normalizar_texto(query)
    q_norm = urllib.parse.quote(f"{texto_limpio}, Antioquia, Colombia")
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={q_norm}&viewbox=-75.68,6.38,-75.48,6.08"
    headers = {'User-Agent': 'Streamlit_Waze_Simulator_Envigado'}
    try:
        resp = requests.get(url, headers=headers, timeout=5).json()
        if resp:
            return float(resp[0]['lat']), float(resp[0]['lon']), resp[0]['display_name'].split(',')[0]
    except Exception:
        pass
    return None, None, None

def obtener_geometria_osrm(puntos):
    """Obtiene trazado vial exacto e instrucciones de giro Waze (steps=true) desde OSRM."""
    if len(puntos) < 2:
        return [[p["lat"], p["lon"]] for p in puntos], 0.0, 0.0, []
    
    coords_str = ";".join([f"{p['lon']},{p['lat']}" for p in puntos])
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson&steps=true"
    
    try:
        resp = requests.get(url, timeout=5).json()
        if resp.get("code") == "Ok":
            ruta = resp["routes"][0]
            geometria = [[lat, lon] for lon, lat in ruta["geometry"]["coordinates"]]
            dist_km = ruta["distance"] / 1000.0
            dur_min = ruta["duration"] / 60.0
            
            pasos = []
            for leg in ruta["legs"]:
                for step in leg["steps"]:
                    nombre_calle = step.get("name", "Vía local")
                    tipo_maniobra = step.get("maneuver", {}).get("type", "continuar")
                    pasos.append(f"{tipo_maniobra.upper()} en {nombre_calle}")
            return geometria, dist_km, dur_min, pasos
    except Exception:
        pass
    
    return [[p["lat"], p["lon"]] for p in puntos], 0.0, 0.0, ["Sin conexión OSRM - Navegando por línea recta"]

# ==========================================
# 3. CONTROL DE ESTADO DE SESIÓN (SESSION STATE)
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "rol" not in st.session_state:
    st.session_state.rol = None
if "cedula" not in st.session_state:
    st.session_state.cedula = ""
if "en_ruta" not in st.session_state:
    st.session_state.en_ruta = False
if "posicion_actual" not in st.session_state:
    st.session_state.posicion_actual = {"lat": 6.1725, "lon": -75.5878}
if "paso_animacion" not in st.session_state:
    st.session_state.paso_animacion = 0

if "puntos_ruta" not in st.session_state:
    st.session_state.puntos_ruta = [
        {"id": 1, "nombre": "Inicio - Base Operativa Parque Envigado", "lat": 6.1725, "lon": -75.5878, "tipo": "Inicio", "completado": False},
        {"id": 2, "nombre": "Giro Cra 43A con Cl 38 Sur", "lat": 6.1740, "lon": -75.5890, "tipo": "Giro", "completado": False},
        {"id": 3, "nombre": "CheckPoint 1 - Contenedores Zona Centro", "lat": 6.1765, "lon": -75.5880, "tipo": "CheckPoint", "completado": False},
        {"id": 4, "nombre": "Giro Cl 36 Sur hacia Vía Creadero", "lat": 6.1780, "lon": -75.5920, "tipo": "Giro", "completado": False},
        {"id": 5, "nombre": "CheckPoint 2 (Zona Rural) - Vereda Las Palmas", "lat": 6.1650, "lon": -75.5600, "tipo": "CheckPoint", "completado": False},
        {"id": 6, "nombre": "Fin - Planta de Transferencia", "lat": 6.1810, "lon": -75.5950, "tipo": "Fin", "completado": False}
    ]

if "alertas_emergencia" not in st.session_state:
    st.session_state.alertas_emergencia = []
if "historial_rutas" not in st.session_state:
    st.session_state.historial_rutas = []

# ==========================================
# 4. MÓDULO DE AUTENTICACIÓN
# ==========================================
def login_screen():
    st.title("🚛 Sistema de Recolección de Residuos - Envigado")
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("📱 **Módulo de Conductor (Móvil)**")
        cc_input = st.text_input("Ingrese su número de Cédula:", key="input_cc")
        if st.button("Iniciar Sesión como Conductor", use_container_width=True):
            if cc_input.strip():
                st.session_state.autenticado = True
                st.session_state.rol = "conductor"
                st.session_state.cedula = cc_input
                st.rerun()
            else:
                st.error("Por favor ingrese un número de cédula válido.")

    with col2:
        st.success("🖥️ **Módulo de Monitoreo Base (PC)**")
        if st.button("Ingresar a la Base de Control", use_container_width=True):
            st.session_state.autenticado = True
            st.session_state.rol = "base"
            st.rerun()

# ==========================================
# 5. VISTA CONDUCTOR (NAVEGACIÓN MÓVIL, WAZE Y OFFLINE)
# ==========================================
def conductor_view():
    st.title(f"📱 Panel Conductor - C.C. {st.session_state.cedula}")

    # Script de persistencia offline en localStorage
    st.components.v1.html("""
    <script>
        function guardarPosicionOffline(lat, lon) {
            let registro = { lat: lat, lon: lon, hora: new Date().toISOString() };
            let rutaLocal = JSON.parse(localStorage.getItem("ruta_offline_envigado") || "[]");
            rutaLocal.push(registro);
            localStorage.setItem("ruta_offline_envigado", JSON.stringify(rutaLocal));
        }

        if (navigator.geolocation) {
            navigator.geolocation.watchPosition(function(pos) {
                guardarPosicionOffline(pos.coords.latitude, pos.coords.longitude);
            }, function(err) {
                console.log("Modo Offline Activo: Guardando posiciones localmente.");
            }, { enableHighAccuracy: true });
        }
    </script>
    """, height=0)

    # Botones principales
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        if not st.session_state.en_ruta:
            if st.button("🟢 INICIAR RUTA (Activar GPS / Offline)", use_container_width=True):
                st.session_state.en_ruta = True
                st.session_state.paso_animacion = 0
                st.rerun()
        else:
            st.warning("📡 RUTA EN PROGRESO (Persistencia Offline Activa)")

    with col_r2:
        if st.button("🚨 BOTÓN DE EMERGENCIA TRÁNSITO", type="primary", use_container_width=True):
            alerta = {
                "conductor": st.session_state.cedula,
                "hora": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "tipo": "Incidente de Tránsito / Bloqueo en Vía"
            }
            st.session_state.alertas_emergencia.append(alerta)
            st.error("🚨 Alerta de emergencia enviada a la Base.")

    # Geometría OSRM e Instrucciones
    geometria, dist_total, tiempo_total, pasos = obtener_geometria_osrm(st.session_state.puntos_ruta)

    # Evaluación de geocercas
    if st.session_state.en_ruta and geometria:
        pos_v = geometria[min(st.session_state.paso_animacion, len(geometria) - 1)]
        st.session_state.posicion_actual = {"lat": pos_v[0], "lon": pos_v[1]}

        for p in st.session_state.puntos_ruta:
            if not p["completado"]:
                dist = calcular_distancia_metros(pos_v[0], pos_v[1], p["lat"], p["lon"])
                if dist <= 25.0:
                    p["completado"] = True
                    st.toast(f"🚨 CHECKPOINT ALCANZADO: {p['nombre']}")

    # Panel de Métricas
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Distancia Total", f"{dist_total:.2f} km")
    col_m2.metric("Tiempo Estimado", f"{tiempo_total:.1f} min")

    # Tarjeta HUD
    if pasos:
        idx_paso = min(int((st.session_state.paso_animacion / max(len(geometria), 1)) * len(pasos)), len(pasos) - 1)
        instruccion_actual = pasos[idx_paso]
    else:
        instruccion_actual = "Calculando ruta..."

    st.info(f"🚘 **HUD Waze:** {instruccion_actual}")

    # Control de Simulación
    if st.session_state.en_ruta:
        col_sim1, col_sim2 = st.columns(2)
        with col_sim1:
            if st.button("▶️ Avanzar Vehículo"):
                if st.session_state.paso_animacion < len(geometria) - 1:
                    st.session_state.paso_animacion += max(1, len(geometria) // 20)
                    st.rerun()
                else:
                    st.success("🏁 ¡Has llegado a tu destino final!")
        with col_sim2:
            if st.button("⏹️ Reiniciar Posición"):
                st.session_state.paso_animacion = 0
                st.rerun()

    # Mapa Interactivo
    m = folium.Map(location=[st.session_state.posicion_actual["lat"], st.session_state.posicion_actual["lon"]], zoom_start=15)
    folium.PolyLine(geometria, color="#0096FF", weight=6, opacity=0.9, tooltip="Ruta Waze").add_to(m)

    folium.Marker(
        [st.session_state.posicion_actual["lat"], st.session_state.posicion_actual["lon"]],
        popup="Vehículo en Trayecto",
        icon=folium.Icon(color="red", icon="truck", prefix="fa")
    ).add_to(m)

    for p in st.session_state.puntos_ruta:
        color_p = "green" if p["completado"] else ("red" if p["tipo"] == "Fin" else "orange")
        folium.Marker(
            [p["lat"], p["lon"]],
            popup=f"<b>{p['tipo']}:</b> {p['nombre']}",
            tooltip=p["nombre"],
            icon=folium.Icon(color=color_p)
        ).add_to(m)

    st_folium(m, width="100%", height=400)

    # Desplegable de Pasos
    with st.expander("📋 Ver Lista Completa de Maniobras de Giro"):
        for i, paso in enumerate(pasos, 1):
            st.write(f"**Paso {i}:** {paso}")

    # Cierre de Ruta
    if st.session_state.en_ruta:
        st.markdown("---")
        st.subheader("🏁 Cierre de Ruta y Registro de Carga")
        with st.form("form_cierre_ruta"):
            toneladas = st.number_input("Toneladas Recolectadas:", min_value=0.0, max_value=60.0, step=0.1)
            capacidad = st.select_slider("Capacidad ocupada del camión:", options=["25%", "50%", "75%", "100% (Capacidad Máxima)"])
            obs = st.text_area("Observaciones (vías bloqueadas, fallas de señal en zona rural, etc.):")

            if st.form_submit_button("🔴 FINALIZAR RUTA Y ENVIAR DATOS"):
                st.session_state.historial_rutas.append({
                    "cedula": st.session_state.cedula,
                    "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "toneladas": toneladas,
                    "capacidad": capacidad,
                    "puntos_totales": len(st.session_state.puntos_ruta),
                    "puntos_completados": sum(1 for p in st.session_state.puntos_ruta if p["completado"]),
                    "observaciones": obs
                })
                st.session_state.en_ruta = False
                st.success("Ruta finalizada. Los datos se sincronizaron con la Base de Control.")
                st.rerun()

# ==========================================
# 6. VISTA BASE DE CONTROL (PC)
# ==========================================
def base_view():
    st.title("🖥️ Base de Control Operativa - Envigado")

    t1, t2, t3, t4 = st.tabs(["📡 Monitoreo en Vivo", "🛠️ Programador de Rutas", "🚨 Emergencias", "📊 Reportes Excel"])

    with t1:
        st.subheader("Ubicación y Avance de Vehículos")
        col_m1, col_m2 = st.columns([3, 1])
        
        geometria, dist_total, tiempo_total, _ = obtener_geometria_osrm(st.session_state.puntos_ruta)

        with col_m1:
            mb = folium.Map(location=[ENVIGADO_LAT, ENVIGADO_LON], zoom_start=13)
            folium.PolyLine(geometria, color="#27ae60", weight=5).add_to(mb)

            for p in st.session_state.puntos_ruta:
                color_p = "green" if p["completado"] else "blue"
                folium.Marker([p['lat'], p['lon']], popup=p['nombre'], icon=folium.Icon(color=color_p)).add_to(mb)

            st_folium(mb, width="100%", height=450)

        with col_m2:
            st.metric("Conductor Activo", f"C.C. {st.session_state.cedula if st.session_state.cedula else 'Sin Asignar'}")
            st.metric("Estado del GPS", "🟢 Transmitiendo" if st.session_state.en_ruta else "🔴 Inactivo")
            st.metric("Puntos Recorridos", f"{sum(1 for p in st.session_state.puntos_ruta if p['completado'])} / {len(st.session_state.puntos_ruta)}")
            st.metric("Distancia Total", f"{dist_total:.2f} km")
            st.metric("Tiempo Estimado", f"{tiempo_total:.1f} min")

    with t2:
        st.subheader("Diseño y Ajuste de Rutas")
        
        st.markdown("#### 1. Programar Parada / Checkpoint (Buscador Waze Aburrá)")
        col_b1, col_b2 = st.columns([3, 1])
        with col_b1:
            input_sitio = st.text_input("Dirección o punto:", placeholder="Ej: Transversal 35C Sur Envigado, Dollarcity, Parque Envigado")
        with col_b2:
            st.write(" ")
            st.write(" ")
            if st.button("➕ Buscar y Cargar"):
                if input_sitio:
                    lat_f, lon_f, nom_f = buscar_lugar_nominatim(input_sitio)
                    if lat_f:
                        st.session_state["temp_lat"] = lat_f
                        st.session_state["temp_lon"] = lon_f
                        st.session_state["temp_nom"] = f"{input_sitio} ({nom_f})"
                        st.success("¡Ubicación encontrada en el Valle de Aburrá!")
                    else:
                        st.error("No se pudo geolocalizar la dirección.")

        st.markdown("---")
        st.markdown("#### 2. Confirmar datos del punto")
        with st.form("form_add_punto"):
            nombre_default = st.session_state.get("temp_nom", "")
            lat_default = st.session_state.get("temp_lat", 6.1750)
            lon_default = st.session_state.get("temp_lon", -75.5900)

            nombre = st.text_input("Nombre / Referencia de Giro:", value=nombre_default)
            lat = st.number_input("Latitud:", value=lat_default, format="%.5f")
            lon = st.number_input("Longitud:", value=lon_default, format="%.5f")
            tipo = st.selectbox("Tipo de Punto:", ["CheckPoint", "Giro", "Inicio", "Fin"])

            if st.form_submit_button("➕ Añadir Punto a la Ruta"):
                st.session_state.puntos_ruta.append({
                    "id": len(st.session_state.puntos_ruta) + 1,
                    "nombre": nombre if nombre else f"Punto {len(st.session_state.puntos_ruta) + 1}",
                    "lat": lat,
                    "lon": lon,
                    "tipo": tipo,
                    "completado": False
                })
                st.success("Punto añadido exitosamente.")
                st.rerun()

        st.subheader("Lista de Puntos Configurados")
        df_puntos = pd.DataFrame(st.session_state.puntos_ruta)
        st.dataframe(df_puntos[["id", "nombre", "tipo", "lat", "lon"]], use_container_width=True)

        if st.button("🗑️ Limpiar / Eliminar Último Punto"):
            if len(st.session_state.puntos_ruta) > 0:
                st.session_state.puntos_ruta.pop()
                st.rerun()

    with t3:
        st.subheader("Alertas de Tránsito Registradas")
        if st.session_state.alertas_emergencia:
            st.table(pd.DataFrame(st.session_state.alertas_emergencia))
        else:
            st.info("No hay alertas activas en este momento.")

    with t4:
        st.subheader("Exportación de Reportes Operativos")
        if st.session_state.historial_rutas:
            df_historial = pd.DataFrame(st.session_state.historial_rutas)
            st.dataframe(df_historial, use_container_width=True)

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_historial.to_excel(writer, sheet_name='Reporte_Rutas', index=False)

            st.download_button(
                label="📥 Descargar Reporte en Excel (.xlsx)",
                data=output.getvalue(),
                file_name=f"Reporte_Recoleccion_Envigado_{datetime.date.today()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("No hay historial de rutas completadas para exportar aún.")

# ==========================================
# 7. CONTROLADOR PRINCIPAL
# ==========================================
def main():
    if st.session_state.autenticado:
        st.sidebar.write(f"Rol Actual: **{st.session_state.rol.upper()}**")
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state.autenticado = False
            st.session_state.rol = None
            st.session_state.cedula = ""
            st.rerun()

        if st.session_state.rol == "conductor":
            conductor_view()
        elif st.session_state.rol == "base":
            base_view()
    else:
        login_screen()

if __name__ == "__main__":
    main()