import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import datetime
import math
import io
import json

# ==========================================
# 1. CONFIGURACIÓN INICIAL Y ESTILOS DE LA APP
# ==========================================
st.set_page_config(
    page_title="Gestión de Rutas de Recolección - Envigado",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Coordenadas centrales de Envigado, Antioquia
ENVIGADO_LAT = 6.17591
ENVIGADO_LON = -75.59174

# ==========================================
# 2. FUNCIONES DE APOYO (GEOCERCAS)
# ==========================================
def calcular_distancia_metros(lat1, lon1, lat2, lon2):
    """Calcula la distancia Haversine en metros entre dos coordenadas."""
    R = 6371000  # Radio de la Tierra en metros
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ==========================================
# 3. CONTROL DE ESTADO DE SESIÓN (SESSION STATE)
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "rol" not in st.session_state:
    st.session_state.rol = None  # "conductor" o "base"
if "cedula" not in st.session_state:
    st.session_state.cedula = ""
if "en_ruta" not in st.session_state:
    st.session_state.en_ruta = False
if "posicion_actual" not in st.session_state:
    st.session_state.posicion_actual = {"lat": 6.1725, "lon": -75.5878}

if "puntos_ruta" not in st.session_state:
    # Ruta base predeterminada (Urbana y Rural hacia Las Palmas)
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
# 4. MODULO DE AUTENTICACIÓN
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
# 5. VISTA CONDUCTOR (NAVEGACIÓN MÓVIL Y OFFLINE)
# ==========================================
def conductor_view():
    st.title(f"📱 Panel Conductor - C.C. {st.session_state.cedula}")

    # SCRIPT DE SOPORTE OFFLINE Y LOCALSTORAGE
    st.components.v1.html("""
    <script>
        // Guardar posiciones localmente si falla la conexión en zonas rurales
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

    # Botones principales de la ruta
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        if not st.session_state.en_ruta:
            if st.button("🟢 INICIAR RUTA (Activar GPS / Offline)", use_container_width=True):
                st.session_state.en_ruta = True
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

    # Geocercas automáticas a 15 metros
    if st.session_state.en_ruta:
        pos_v = st.session_state.posicion_actual
        for p in st.session_state.puntos_ruta:
            if not p["completado"]:
                dist = calcular_distancia_metros(pos_v["lat"], pos_v["lon"], p["lat"], p["lon"])
                if dist <= 15:
                    p["completado"] = True
                    st.toast(f"✅ ¡Geocerca! Punto completado automáticamente: {p['nombre']}")

    # Renderizado de Mapa Guiado
    m = folium.Map(location=[ENVIGADO_LAT, ENVIGADO_LON], zoom_start=14, tiles="OpenStreetMap")
    coords_ruta = [[p["lat"], p["lon"]] for p in st.session_state.puntos_ruta]
    folium.PolyLine(coords_ruta, color="blue", weight=5, opacity=0.85, tooltip="Ruta de Recolección").add_to(m)

    for p in st.session_state.puntos_ruta:
        color_p = "green" if p["completado"] else ("red" if p["tipo"] == "Fin" else "orange")
        icon_p = "ok-sign" if p["completado"] else "info-sign"
        folium.Marker(
            [p["lat"], p["lon"]],
            popup=p["nombre"],
            tooltip=p["nombre"],
            icon=folium.Icon(color=color_p, icon=icon_p)
        ).add_to(m)

    st_folium(m, width="100%", height=400)

    # Formulario de Finalización y Tonelaje
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

    # Pestaña 1: Monitoreo
    with t1:
        st.subheader("Ubicación y Avance de Vehículos")
        col_m1, col_m2 = st.columns([3, 1])
        with col_m1:
            mb = folium.Map(location=[ENVIGADO_LAT, ENVIGADO_LON], zoom_start=13)
            coords = [[p["lat"], p["lon"]] for p in st.session_state.puntos_ruta]
            folium.PolyLine(coords, color="green", weight=4).add_to(mb)

            for p in st.session_state.puntos_ruta:
                folium.Marker([p['lat'], p['lon']], popup=p['nombre']).add_to(mb)

            st_folium(mb, width="100%", height=450)

        with col_m2:
            st.metric("Conductor Activo", f"C.C. {st.session_state.cedula if st.session_state.cedula else 'Sin Asignar'}")
            st.metric("Estado del GPS", "🟢 Transmitiendo" if st.session_state.en_ruta else "🔴 Inactivo")
            st.metric("Puntos Recorridos", f"{sum(1 for p in st.session_state.puntos_ruta if p['completado'])} / {len(st.session_state.puntos_ruta)}")

    # Pestaña 2: Programación de Puntos
    with t2:
        st.subheader("Diseño y Ajuste de Rutas")
        with st.form("form_add_punto"):
            st.write("**Agregar Punto de Referencia o Giro:**")
            nombre = st.text_input("Nombre / Referencia de Giro:")
            lat = st.number_input("Latitud:", value=6.1750, format="%.5f")
            lon = st.number_input("Longitud:", value=-75.5900, format="%.5f")
            tipo = st.selectbox("Tipo de Punto:", ["Giro", "CheckPoint", "Inicio", "Fin"])

            if st.form_submit_button("➕ Añadir Punto a la Ruta"):
                st.session_state.puntos_ruta.append({
                    "id": len(st.session_state.puntos_ruta) + 1,
                    "nombre": nombre,
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

        if st.button("🗑️ Eliminar Último Punto"):
            if len(st.session_state.puntos_ruta) > 0:
                st.session_state.puntos_ruta.pop()
                st.rerun()

    # Pestaña 3: Emergencias
    with t3:
        st.subheader("Alertas de Tránsito Registradas")
        if st.session_state.alertas_emergencia:
            st.table(pd.DataFrame(st.session_state.alertas_emergencia))
        else:
            st.info("No hay alertas activas en este momento.")

    # Pestaña 4: Reportes Excel
    with t4:
        st.subheader("Exportación de Reportes Operativos")
        if st.session_state.historial_rutas:
            df_historial = pd.DataFrame(st.session_state.historial_rutas)
            st.dataframe(df_historial, use_container_width=True)

            # Generar archivo Excel en memoria
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