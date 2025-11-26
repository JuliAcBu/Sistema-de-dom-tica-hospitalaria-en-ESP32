import machine
import time
import dht
import network
import urequests
import struct
import socket
import micropython
import gc
import json

# Limpieza inicial
gc.collect()
micropython.alloc_emergency_exception_buf(100)

SSID = "Redmi 13"
PASS = "holaanny"

BOT_TOKEN = "7451723561:AAHVb5QhIVkMpjA6-utZG_jiIcydAQtLdsg"
CHAT_ID_MASTER = 8577317562 

# Umbrales
TEMP_MIN = 27
TEMP_MAX = 31  
GAS_PELIGRO = 360
LUZ_OSCURA = 3800
PUERTA_UMB = 350

# MENSAJE DE AYUDA (MENU)
MENU_AYUDA = """
🤖 *LISTA DE COMANDOS:*

📡 *CONSULTAS*
/estado - Ver sensores y sistema

🚨 *ALARMAS*
/silenciar - Apagar sirena/buzzer

⚙️ *MODOS*
/auto - Modo Automático (Sensores deciden)
/manual - Modo Manual (Tú decides)

💡 *ACCIONES MANUALES*
/luz on  |  /luz off
/vent on |  /vent off
/calef on|  /calef off
"""

dht_sensor = dht.DHT11(machine.Pin(25))
mq135 = machine.ADC(machine.Pin(34)); mq135.atten(machine.ADC.ATTN_11DB)
sensor_luz = machine.ADC(machine.Pin(35)); sensor_luz.atten(machine.ADC.ATTN_11DB)
boton = machine.Pin(18, machine.Pin.IN, machine.Pin.PULL_DOWN)
i2c = machine.I2C(0, sda=machine.Pin(21), scl=machine.Pin(22))
MPU_ADDR = 0x68

buzzer = machine.Pin(16, machine.Pin.OUT)
rgb_r = machine.Pin(14, machine.Pin.OUT)
rgb_g = machine.Pin(12, machine.Pin.OUT)
rgb_b = machine.Pin(15, machine.Pin.OUT)

vent_1 = machine.Pin(27, machine.Pin.OUT); vent_2 = machine.Pin(23, machine.Pin.OUT)
luz_1 = machine.Pin(32, machine.Pin.OUT); luz_2 = machine.Pin(13, machine.Pin.OUT)
calef_1 = machine.Pin(26, machine.Pin.OUT); calef_2 = machine.Pin(4, machine.Pin.OUT)

estado = {
    "t": 0, "h": 0, "gas": 0, "luz": 0, "puerta": "CERRADA",
    "calef": False, "vent": False, "bomb": False,
    "modo_manual": False,
    "sistema": "NORMAL"
}
boton_presionado = False
offset_telegram = 0

def isr_boton(pin):
    global boton_presionado
    boton_presionado = True
boton.irq(trigger=machine.Pin.IRQ_RISING, handler=isr_boton)

def set_rgb(color):
    rgb_r.off(); rgb_g.off(); rgb_b.off()
    if color == "OK": rgb_g.on()
    elif color == "ALERTA": rgb_r.on()
    elif color == "INFO": rgb_b.on()

def activar(p1, p2, on):
    if on: p1.on(); p2.off()
    else: p1.off(); p2.off()

def leer_puerta():
    try:
        i2c.writeto_mem(MPU_ADDR, 0x6B, b'\x00')
        val = struct.unpack(">h", i2c.readfrom_mem(MPU_ADDR, 0x3B, 2))[0]
        return abs(val)
    except: return -1

def conectar_wifi():
    w = network.WLAN(network.STA_IF); w.active(True)
    if not w.isconnected():
        print(f"Conectando a {SSID}...")
        w.connect(SSID, PASS)
        retry = 0
        while not w.isconnected() and retry < 20:
            time.sleep(0.5); retry+=1
    return w.ifconfig()[0]

def telegram_enviar(msj):
    try:
        gc.collect()
        print(f">> TG: {msj}")
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {'chat_id': CHAT_ID_MASTER, 'text': msj, 'parse_mode': 'Markdown'}
        r = urequests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
        r.close()
    except Exception as e: print(f"Error TG: {e}")

def telegram_procesar():
    global offset_telegram, estado
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset_telegram + 1}&limit=1&timeout=2"
        res = urequests.get(url)
        datos = res.json()
        res.close()

        if "result" in datos and len(datos["result"]) > 0:
            for update in datos["result"]:
                offset_telegram = update["update_id"]
                
                if "message" in update and "text" in update["message"]:
                    texto_recibido = update["message"]["text"].lower().strip()
                    print(f"📩 CMD: {texto_recibido}")

                    if texto_recibido == "/start" or texto_recibido == "ayuda":
                        telegram_enviar(MENU_AYUDA)

                    elif texto_recibido == "/estado" or texto_recibido == "estado":
                        rpt = f"*ESTADO ACTUAL:*\n🌡 T: {estado['t']}C | 💧 H: {estado['h']}%\n☣ Gas: {estado['gas']} | ☀️ Luz: {estado['luz']}\n🚪 Puerta: {estado['puerta']}\n⚙️ Modo: {'MANUAL' if estado['modo_manual'] else 'AUTO'}"
                        telegram_enviar(rpt)

                    elif texto_recibido == "/silenciar" or texto_recibido == "silenciar":
                        buzzer.off()
                        set_rgb("INFO")
                        estado['sistema'] = "SILENCIADO"
                        telegram_enviar("🔕 *ALARMA SILENCIADA*")

                    elif texto_recibido == "/auto" or texto_recibido == "auto":
                        estado['modo_manual'] = False
                        telegram_enviar("✅ *SISTEMA EN MODO AUTOMÁTICO*")

                    elif texto_recibido == "/manual" or texto_recibido == "manual":
                        estado['modo_manual'] = True
                        telegram_enviar("🔧 *SISTEMA EN MODO MANUAL*\nUsa /luz on, /vent on, etc.")

                    elif "/luz" in texto_recibido:
                        estado['modo_manual'] = True
                        if "on" in texto_recibido: estado['bomb'] = True
                        else: estado['bomb'] = False
                        activar(luz_1, luz_2, estado['bomb'])
                        telegram_enviar(f"💡 Luz: {'ON' if estado['bomb'] else 'OFF'}")

                    elif "/vent" in texto_recibido:
                        estado['modo_manual'] = True
                        if "on" in texto_recibido: estado['vent'] = True
                        else: estado['vent'] = False
                        activar(vent_1, vent_2, estado['vent'])
                        telegram_enviar(f"💨 Ventilador: {'ON' if estado['vent'] else 'OFF'}")

                    elif "/calef" in texto_recibido:
                        estado['modo_manual'] = True
                        if "on" in texto_recibido: estado['calef'] = True
                        else: estado['calef'] = False
                        activar(calef_1, calef_2, estado['calef'])
                        telegram_enviar(f"🔥 Calefacción: {'ON' if estado['calef'] else 'OFF'}")
                    
                    else:
                        telegram_enviar("❓ Comando no reconocido. Escribe /start para ver la lista.")

    except: print("Error lectura TG")

# ==========================================
#       6. PÁGINA WEB (AQUÍ ESTÁN LOS EMOJIS NUEVOS)
# ==========================================
def pagina_web():
    h = f"""<!DOCTYPE html><html><head>
    <meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
    <title>Hospital SDH</title>
    <style>
    body{{font-family:Arial,sans-serif;background:#eef2f3;text-align:center;padding:10px;margin:0}}
    h2{{color:#333;margin-bottom:5px}}
    .card{{background:white;border-radius:12px;padding:15px;margin:15px auto;max-width:400px;box-shadow:0 4px 8px rgba(0,0,0,0.1)}}
    .row{{display:flex;justify-content:space-around;margin:10px 0}}
    .val{{font-size:1.2em;font-weight:bold;color:#007bff}}
    .btn{{width:46%;padding:12px;margin:5px 1%;border:none;border-radius:8px;color:white;font-size:15px;cursor:pointer}}
    .full{{width:96%}}
    .on{{background:#28a745}} .off{{background:#dc3545}} .blue{{background:#007bff}}
    </style>
    <script>
    function c(v){{ fetch('/cmd?v='+v).then(()=>location.reload()); }}
    setInterval(()=>location.reload(), 5000); 
    </script>
    </head><body>

    <div class='card'>
        <h2>🏥 Habitación 101</h2>
        <hr>
        <div class='row'>
            <div>🌡 Temp<br><span class='val'>{estado['t']}°C</span></div>
            <div>💧 Hum<br><span class='val'>{estado['h']}%</span></div>
        </div>
        <div class='row'>
            <div>☣️ Gas<br><span class='val'>{estado['gas']}</span></div>
            <div>☀️ Luz<br><span class='val'>{estado['luz']}</span></div>
        </div>
        <p>🚪 Puerta: <b>{estado['puerta']}</b></p>
        <p>📊 Estado: <b>{estado['sistema']}</b></p>
    </div>

    <div class='card'>
        <h3>⚙️ {'MANUAL' if estado['modo_manual'] else 'AUTOMÁTICO'}</h3>
        <button class='btn blue full' onclick="c('mode')">🔄 Cambiar Modo</button><br>
        <button class='btn {"on" if estado['vent'] else "off"}' onclick="c('vent')">💨 Ventilador</button>
        <button class='btn {"on" if estado['calef'] else "off"}' onclick="c('calef')">🔥 Calefactor</button><br>
        <button class='btn {"on" if estado['bomb'] else "off"} full' onclick="c('bomb')">💡 Luz Techo</button>
    </div>
    </body></html>"""
    return h

#       7. BUCLE PRINCIPAL
try:
    ip = conectar_wifi()
    print(f"--- ONLINE: http://{ip} ---")
    telegram_enviar(f"✅ *SISTEMA ONLINE*\nIP Web: http://{ip}")
    time.sleep(1)
    telegram_enviar(MENU_AYUDA)
except: print("Fallo WiFi")

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('', 80))
s.listen(5)
s.settimeout(0.001)

timer_sens = 0
timer_tg = 0

def atender_web():
    try:
        conn, addr = s.accept()
        req = conn.recv(1024).decode()
        if "/cmd?v=mode" in req: estado['modo_manual'] = not estado['modo_manual']
        elif "/cmd?v=vent" in req: estado['modo_manual']=True; estado['vent']=not estado['vent']; activar(vent_1, vent_2, estado['vent'])
        elif "/cmd?v=bomb" in req: estado['modo_manual']=True; estado['bomb']=not estado['bomb']; activar(luz_1, luz_2, estado['bomb'])
        elif "/cmd?v=calef" in req: estado['modo_manual']=True; estado['calef']=not estado['calef']; activar(calef_1, calef_2, estado['calef'])
        conn.send('HTTP/1.1 200 OK\nContent-Type: text/html\n\n' + pagina_web())
        conn.close()
    except: pass

while True:
    try:
        # 1. WEB 
        atender_web()

        # 2. SENSORES (1s)
        if time.time() - timer_sens > 1:
            try: dht_sensor.measure(); estado['t']=dht_sensor.temperature(); estado['h']=dht_sensor.humidity()
            except: pass
            estado['gas'] = mq135.read()
            estado['luz'] = sensor_luz.read()
            mov = leer_puerta()
            puerta_abierta = mov > PUERTA_UMB or mov == -1
            estado['puerta'] = "ABIERTA" if puerta_abierta else "CERRADA"

            if not estado['modo_manual']:
                # AUTOMÁTICO
                # Calefacción (Por Temp Minima)
                activar(calef_1, calef_2, estado['t'] < TEMP_MIN)
                
                # Ventilador (Por Gas O Por Temp Maxima) <--- CAMBIO AQUI
                condicion_vent = (estado['gas'] > GAS_PELIGRO) or (estado['t'] > TEMP_MAX)
                activar(vent_1, vent_2, condicion_vent)
                
                # Luz (Por oscuridad y puerta)
                activar(luz_1, luz_2, (estado['luz'] < LUZ_OSCURA and puerta_abierta))
                
                # Actualizar diccionarios
                estado['calef'] = estado['t'] < TEMP_MIN
                estado['vent'] = condicion_vent
                estado['bomb'] = (estado['luz'] < LUZ_OSCURA and puerta_abierta)

            # Alarmas y Avisos
            if boton_presionado:
                set_rgb("ALERTA"); buzzer.on(); telegram_enviar("🚨 *¡BOTÓN DE PÁNICO!*"); boton_presionado = False
                estado['sistema'] = "ALERTA"
            elif estado['gas'] > GAS_PELIGRO:
                set_rgb("ALERTA"); buzzer.on(); estado['sistema'] = "PELIGRO GAS"
                if int(time.time()) % 30 == 0: telegram_enviar(f"☣️ *FUGA DE GAS: {estado['gas']}*")
            elif puerta_abierta: set_rgb("INFO"); buzzer.off(); estado['sistema'] = "PUERTA ABIERTA"
            else: 
                if estado['sistema'] != "SILENCIADO":
                    set_rgb("OK"); buzzer.off(); estado['sistema'] = "NORMAL"
            
            # SHELL DE THONNY
            print(f"[SHELL] T:{estado['t']}C | H:{estado['h']}% | Gas:{estado['gas']} | Luz:{estado['luz']} | Puerta:{estado['puerta']} | Sys:{estado['sistema']}")

            timer_sens = time.time()
          
        # 3. WEB OTRA VEZ
        atender_web()

        # 4. TELEGRAM (6s)
        if time.time() - timer_tg > 6:
            telegram_procesar()
            timer_tg = time.time()
            
    except Exception as e: print("Error Loop:", e)