from machine import Pin, PWM, Timer
import machine
import time
import network
from simple import MQTTClient

# ----------------------------
# ---- VARIJABLE I PINOVI ----
# ----------------------------
door_open = False # varijabla stanja
# Servo setup
servo_pin = Pin(16)
servo = PWM(servo_pin)
servo.freq(50)
# Senzor vani setup
TRIGGER_PIN = 3
ECHO_PIN = 2
BRZINA_ZVUKA = 0.0343 # u cm po mikrosekundi
trigger = Pin(TRIGGER_PIN, Pin.OUT)
echo = Pin(ECHO_PIN, Pin.IN)
signal_on = 0
distanca = 0
# Touch senzor
touch_pin = Pin(5, Pin.IN)

# ----------------
# ---- TIMERI ----
# ----------------
timer_senzor = Timer()
timer_close_safe = Timer()
# periodi u ms
TIMER_CLOSE_MS = 120000
TIMER_SENZOR_MS = 1000

# ---------------------
# ---- WIFI I MQTT ----
# ---------------------
# Wifi podaci
ssid = 'ETF-WiFi-Guest'
password = ''
# MQTT konekcija
client_id = 'pico-client-dalila196657'
broker = 'broker.hivemq.com'
client = MQTTClient(client_id, broker)
# MQTT teme
T_INIT = b'garaza/validacija/start'
T_VRATA = b'garaza/vrata'


# ------------------
# ---- FUNKCIJE ----
# ------------------

# Wi-Fi konekcija
def connect_wifi():
    # inicijalizacija 
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print('Već povezan na mrežu:', wlan.ifconfig())
    else:
        # povezi se ako nije vec povezan
        print('Povezujem se na mrežu...')
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            time.sleep(1)
        print('Povezan na mrežu:', wlan.ifconfig())

# Mjeri distancu od objekta
# ISR za timer
def mjeri(timer):
     global signal_on, trigger, echo
     # salje se kratki puls na trigger
     trigger.off(); time.sleep_us(2)
     trigger.on(); time.sleep_us(10)
     trigger.off()
     
     try:
          # slusanje na echo
          # signal_on = vrijeme u mikrosekundama
          # vrijeme za koje je echo pin imao vrijednost high
          signal_on = machine.time_pulse_us(echo, 1, 10000000)
     except OSError:
          print("Timeout dok echo nije na HIGH - nema objekta")
          return

    # sa brzinom zvuka dobije se distanca u cm
    # dijeli se sa 2 jer nam treba distanca u jednom smjeru samo
     distanca = (signal_on * BRZINA_ZVUKA)/2
     print("Distanca od objekta je ", distanca, "cm")
     if distanca < 7:
        # automobil se priblizio dovoljno
        # validacija unosa moze da pocne
        # javljamo vanjskom modulu putem MQTT
        timer_senzor.deinit() # vise ne treba senzor udaljenosti
        client.publish(T_INIT, b'start', retain = False)

# Funkcija za mapiranje ugla u PWM duty
def mapiranje_intervala(x, ulazni_min, ulazni_max, izlazni_min, izlazni_max):
    return (x - ulazni_min) * (izlazni_max - izlazni_min)/(ulazni_max - ulazni_min) + izlazni_min

# Kontrola servo motora
def pisi_servo(pin, ugao):
    puls = mapiranje_intervala(ugao, 0, 180, 0.5, 2.5)  # ms
    duty = int(mapiranje_intervala(puls, 0, 20, 0, 65535))  # konvertuje u 16-bitni duty
    pin.duty_u16(duty)

# Funkcije za otvaranje i zatvaranje vrata
def open_door():
    global door_open
    print("Otvaram vrata...")
    door_open = True # postavi varijablu stanja
    pisi_servo(servo, 180)  # potpuno otvoreno
    # inicijaliziraj timer
    # ako vrata nisu zatvorena nakon 2 min, zatvara ih njegov ISR
    timer_close_safe.init(period = TIMER_CLOSE_MS, mode=Timer.ONE_SHOT, callback = safe_close)

def close_door():
    global door_open
    print("Zatvaram vrata...")
    door_open = False
    pisi_servo(servo, 80)  # zatvoreno, nije 90 zbog koristenog servo motora, ovo je bolje odgovaralo
    # dosli smo u stanje gdje bi ponovo mogla trebati validacija unosa
    # aktiviramo senzor udaljenosti za tu svrhu
    timer_senzor.init(period = TIMER_SENZOR_MS, mode = Timer.PERIODIC, callback = mjeri)

# Setup MQTT klijenta
def mqtt_setup():
    # spoji se na wifi i pretplati se na temu s koje slusas poruke
    connect_wifi()
    client.set_callback(sub_cb)
    client.connect()
    client.subscribe(T_VRATA)
    print("Spreman za primanje MQTT poruka...")

# MQTT callback
def sub_cb(topic, msg):
    # MQTT klijent prima poruke sa teme garaza/vrata
    # sluzi za kontrolu vrata
    print("Poruka primljena:", topic.decode(), msg.decode())
    if msg.decode() == "open":
        open_door()
        print("Otvaram vrata")
    elif msg.decode() == "close":
        close_door()
        print("Zatvaram vrata")

# ISR za touch senzor
def touch_senzor(pin):
    # radi suprotnu akciju od trenutnog stanja garaznih vrata
    if door_open:
        close_door()
        print("Zatvaram vrata")
    else:
        open_door()
        print("Otvaram vrata")
    
# ISR za timer automatskog zatvaranja
# Ako su vrata ostala otvorena nakon 2 min zatvaraju se automatski
def safe_close(timer):
    if door_open:
        close_door()

# ------------------------
# ---- POCETNO STANJE ----
# ------------------------
mqtt_setup()
close_door()
print("Zatvaram vrata")
timer_senzor.init(period = TIMER_SENZOR_MS, mode = Timer.PERIODIC, callback = mjeri)
touch_pin.irq(handler = touch_senzor, trigger = Pin.IRQ_RISING)

# Glavna petlja
# provjeravanje MQTT poruke
while True:
    client.check_msg()
    time.sleep(0.05)