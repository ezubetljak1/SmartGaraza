
from machine import Pin, Timer
import time, network
from umqtt_simple import MQTTClient
from mfrc522 import MFRC522
import urandom

# ----------------------------
# ---- VARIJABLE I PINOVI ----
# ----------------------------
# Generator zvuka
piezo = Pin(28, Pin.OUT)
piezo.low()

# Displej i tastatura
row_pins   = [Pin(p, Pin.OUT)             for p in (21,22,26,27)]
col_pins   = [Pin(p, Pin.IN, Pin.PULL_DOWN) for p in (0,1,2,3)]
digit_pins = [Pin(p, Pin.OUT)             for p in (4,5,6,7)]
seg_pins   = [Pin(p, Pin.OUT, Pin.PULL_UP) for p in (8,9,10,11,12,13,14)]
dp_pin     = Pin(15, Pin.OUT, Pin.PULL_UP)
dp_pin.value(1)

# RFID citac
reader = MFRC522(spi_id=0, sck = 18, cs =17, miso = 16, mosi=19, rst=20)

# ---- Varijable stanja ----
started = False # da li je zapocela validacija
input_pin = "" # ulazni pin koji se unosi 
_last_rc = (None, None) # prosla kombinacija red kolona
_streak = 0 # trenutni streak znakova
_debounced_rc = (None, None) 
current_digit = 0 # za multipleksiranje displeja
wrong_attempts = 0 # pogresni pokusaji unosa
alarm_active = False # je li alarm aktivan

# ---- Konstante ----
# Displej
DISPLEJ_MAPA = {
    0:(0,0,0,0,0,0,1), 1:(1,0,0,1,1,1,1), 2:(0,0,1,0,0,1,0),
    3:(0,0,0,0,1,1,0), 4:(1,0,0,1,1,0,0), 5:(0,1,0,0,1,0,0),
    6:(0,1,0,0,0,0,0), 7:(0,0,0,1,1,1,1), 8:(0,0,0,0,0,0,0),
    9:(0,0,0,0,1,0,0),
}

BLANK = (1,1,1,1,1,1,1)
MINUS = (1,1,1,1,1,1,0)

# Tastatura
matrix_keys = [
    ['1','2','3','A'],
    ['4','5','6','B'],
    ['7','8','9','C'],
    ['*','0','#','D']
]

DEBOUNCE_STREAK = 4

# RFID i PIN
DOZVOLJENA_KARTICA = "4159772003"
ISPRAVAN_PIN = '8273'

# ----------------
# ---- TIMERI ----
# ----------------
timer_keypad = Timer()
timer_display = Timer()
timer_mqtt = Timer()
# periodi u ms
SCAN_INTERVAL   = 20   
MUX_INTERVAL    = 5   
RFID_INTERVAL = 1500 

# ---------------------
# ---- WIFI I MQTT ----
# ---------------------
# WiFi podaci
SSID = 'ETF-WiFi-Guest'
PASSWORD = ''
# MQTT konekcija
BROKER = 'broker.hivemq.com'
random_suffix = "%04d" % (urandom.getrandbits(16) % 10000)
CLIENT_ID = b'picoETF_garaza' + random_suffix.encode()
client = MQTTClient(CLIENT_ID, BROKER)
# MQTT teme
T_ALARM_ACTIVE = b'garaza/alarm/aktivan'
T_ALARM = b'garaza/alarm/ugasiti'
T_VRATA = b'garaza/vrata'
T_USER = b'garaza/vrata/user'
T_INIT = b'garaza/validacija/start'


# ------------------
# ---- FUNKCIJE ----
# ------------------

# --- RFID CITAC ----
def rfid_callback():
    reader.init()
    # posalji zahtjev za citanje
    (stat, tag_type) = reader.request(reader.REQIDL)
    if stat == reader.OK:
        # procitaj karticu i dobij uid
        (stat, uid) = reader.SelectTagSN()
        # je li ispravno procitana?
        if stat == reader.OK:
            # broj prislonjene kartice
            card = int.from_bytes(bytes(uid), "little", False)
            if str(card) != DOZVOLJENA_KARTICA:
                # nedozvoljen pokusaj ulaza
                start_alarm()
            else:
                # ispravna kartica, kratki zvuk
                kratki_bip()
                print("Pisem da se vrata otvore i koji korisnik")
                # javi unutrasnjem modulu da otvori vrata
                # javi koji je korisnik za mobilnu aplikaciju
                client.publish(T_VRATA, b'open', retain=False)
                client.publish(T_USER, b'4159772003', retain=False)

# ---- Wifi konekcija ----
def connect_wifi():
    # inicijaliacija
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        # spoji ako nije vec spojen
        print("Spajam na WiFi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.2)
    print("WiFi konfiguracija:", wlan.ifconfig())

# ---- MQTT Callback ----
def on_mqtt(topic, msg):
    # prima poruke za gasenje alarma i pocetak validacije 
    global alarm_active, started
    print("MQTT primljeno:", topic, msg)
    if topic == T_ALARM and msg.strip() == b'alarm_off':
        if alarm_active:
            print("Gasi alarm")
            stop_alarm()
        else:
            print("Alarm nije aktivan, ništa za gasiti")
    
    elif topic == T_INIT and msg.strip()==b'start':
        # zapocni validaciju unosa
        timer_keypad.init(period=SCAN_INTERVAL, mode=Timer.PERIODIC, callback=scan_keypad)
        timer_display.init(period=MUX_INTERVAL, mode=Timer.PERIODIC, callback=display_callback)
        started = True

# ---- Setup za MQTT ----
def mqtt_setup():
    connect_wifi()
    client.set_callback(on_mqtt)
    print("Callback postavljen za mqtt")

    while True:
        try:
            print("Pokušaj spajanja klijenta...")
            client.connect()
            print("Klijent uspješno spojen")
            client.subscribe(T_ALARM)
            print("Pretplaćen na topic", T_ALARM)
            client.subscribe(T_INIT)
            print("Pretplaćen na topic", T_INIT)
            break  # izlaz iz petlje ako je uspješno
        except Exception as e:
            print("MQTT greška pri spajanju:", e)
            time.sleep(2)  # pričekaj malo prije novog pokušaja


# --- ALARM KONTROLA ---
def start_alarm():
    global alarm_active
    if alarm_active:
        print("Alarm je već aktivan")
        return
    alarm_active = True
    print("Alarm startovan")
    piezo.high()
    # ukljucen alarm, onemogucen unos
    timer_keypad.deinit()
    timer_display.deinit()
    client.publish(T_ALARM_ACTIVE, b'aktivan', retain=False)

def stop_alarm():
    global alarm_active
    alarm_active = False
    piezo.low()
    print("Alarm ugašen")
    # zaustavi alarm i ponovo omoguci unos
    timer_keypad.init(period=SCAN_INTERVAL, mode=Timer.PERIODIC, callback=scan_keypad)
    timer_display.init(period=MUX_INTERVAL, mode=Timer.PERIODIC, callback=display_callback)

# --- Displej ISR ---
def display_callback(timer):
    # postavlja vrijednost trenutne cifre po redu
    global current_digit, input_pin
    for d in digit_pins: d.value(1)
    for s in seg_pins:   s.value(1)
    dp_pin.value(1)
    s = input_pin + " "*(4 - len(input_pin))
    ch = s[current_digit]
    if ch == ' ':
        seg = BLANK
    elif ch == '-':
        seg = MINUS
    else:
        try:
            # dobij vrijednost segmenata
            seg = DISPLEJ_MAPA.get(int(ch), BLANK)
        except:
            seg = BLANK
    # postavi vrijednosti segmenata
    for i,v in enumerate(seg):
        seg_pins[i].value(v)
    # ukljuci cifru i racunaj koja je iduca po redu
    digit_pins[current_digit].value(0)
    current_digit = (current_digit + 1) & 3

# --- SKENIRANJE TASTATURE ---

# jedan two-way prolaz
def single_scan():
    cand = (None, None)
    # postavi jedan po jedan red na high
    # provjeri ima li kolona da je high
    for ri, rp in enumerate(row_pins):
        rp.high()
        time.sleep_us(3)
        cols = [cp.value() for cp in col_pins]
        rp.low()
        act = [i for i,v in enumerate(cols) if v]
        if len(act)==1:
            cand = (ri, act[0])
            break
        # detektovan je ghosting, prekini
        if len(act)>1:
            return (None,None,None)
    if cand[0] is None:
        return (None,None,None)
    ri,ci = cand
    # rekonfiguracija pinova
    for rp in row_pins: rp.init(Pin.IN, Pin.PULL_DOWN)
    for cp in col_pins: cp.init(Pin.OUT)
    # drugi prolaz, sada sa novom konfiguracijom
    for i,cp in enumerate(col_pins):
        cp.value(1 if i==ci else 0)
    time.sleep_us(3)
    rows_back = [rp.value() for rp in row_pins]
    # vrati izvornu konfiguraciju
    for rp in row_pins: rp.init(Pin.OUT); rp.low()
    for cp in col_pins: cp.init(Pin.IN, Pin.PULL_DOWN)
    # tipka detektovana ispravno
    if rows_back.count(1)==1 and rows_back[ri]==1:
        return (ri,ci, matrix_keys[ri][ci])
    return (None,None,None)

# ISR za skeniranje tastature
def scan_keypad(timer):
    # potrebno 4 puta uzastopno detektovati istu tipku da se prihvati
    global _last_rc, _streak, _debounced_rc
    # jedan two-way prolaz
    r,c,key = single_scan()
    raw = (r,c)
    if raw==_last_rc:
        _streak += 1 # povecaj streak
    else:
        _last_rc, _streak = raw,1 # streak je na 1
    
    # Ako je postignut trazeni streak od 4
    if _streak>=DEBOUNCE_STREAK:
        if _debounced_rc==(None,None) and raw!=(None,None):
            _debounced_rc = raw
            # Regulisi parsiranje pina
            handle_key(key)
        elif _debounced_rc!=(None,None) and raw==(None,None):
            _debounced_rc = (None,None)

# Blinkanje znaka - na pogresnom unosu
def blink_minus(duration=2, interval=0.3):
    timer_display.deinit()
    end_time = time.time() + duration
    while time.time() < end_time:
        for d in digit_pins: d.value(1)
        for s in seg_pins:   s.value(1)
        dp_pin.value(1)
        time.sleep(interval)
        # sve cifre na -
        for d in digit_pins:
            for i, v in enumerate(MINUS):
                seg_pins[i].value(v)
            d.value(0)
        time.sleep(interval)
        for d in digit_pins: d.value(1)
    # ponovo omoguci prikaz displeja
    timer_display.init(period=MUX_INTERVAL, mode=Timer.PERIODIC, callback=display_callback)

def clear_display():
    # gasi sve segmente
    for digit in digit_pins:
        digit.value(1)

    for seg in seg_pins:
        seg.value(1)  

    dp_pin.value(1)

# Blinkanje znaka . na ispravnom unosu
def flash_decimal_points(duration=2):
    timer_display.deinit()
    t_end = time.ticks_add(time.ticks_ms(), duration * 1000)

    while time.ticks_diff(t_end, time.ticks_ms()) > 0:
        # Uključi samo DP na svim ciframa
        for i in range(4):
            clear_display()  
            digit_pins[i].value(0)  
            dp_pin.value(0)  
            time.sleep(0.005)
            dp_pin.value(1) 
            digit_pins[i].value(1)  
        time.sleep(0.2)  
    timer_display.init(period=MUX_INTERVAL, mode=Timer.PERIODIC, callback=display_callback)

# Parsiranje PIN-a
def handle_key(key):
    global input_pin, wrong_attempts
    if key=='#':
        # pokusaj potvrde unosa
        # vidi je li duzina pina ispravna i je li ispravan pin
        if len(input_pin) == 4:
            if input_pin == ISPRAVAN_PIN:
                print("Ispravan PIN, alarm ne aktivira se")
                wrong_attempts = 0
                # Prikazi ispravno stanje
                flash_decimal_points()
                kratki_bip()
                print("Pisem da se vrata otvore i user")
                # javi unutrasnjem modulu da otvori vrata
                # javi koji je user zbog mobilne aplikacije
                client.publish(T_VRATA, b'open', retain=False)
                client.publish(T_USER, b'8273', retain=False)
            else:
                # neispravan pokusaj, prikazi stanje
                wrong_attempts += 1
                blink_minus()
                print("Pogrešan PIN, ", wrong_attempts)
                # na trecem uzastopnom se pali alarm
                if wrong_attempts == 3: 
                    wrong_attempts = 0
                    start_alarm()
            input_pin = ""
        else:
            input_pin = ""
    elif key=='*':
        input_pin = ""
    elif key.isdigit() and len(input_pin)<4:
        input_pin += key

# Kratka zvucna potvrda ispravnog unosa
def kratki_bip():
    piezo.high()
    time.sleep(0.5)
    piezo.low()

# ------------------------
# ---- POCETNO STANJE ----
# ------------------------
mqtt_setup()
last_rfid_check = time.ticks_ms()

# Glavna petlja
while True:
    # desava se da klijent gubi konekciju s temom
    # ovo je odrzava zivom
    client.subscribe(T_ALARM)
    # ako nije zapoceta validacija provjeravaj i tu temu
    if not started:
        client.subscribe(T_INIT)
    # provjeri poruku
    client.check_msg()
    # skeniraj RFID
    # ako je zapocela validacija
    # ako alarm nije aktivan
    # i ako je prosla 1.5 s
    if started and not alarm_active and time.ticks_diff(time.ticks_ms(), last_rfid_check) > RFID_INTERVAL:
        rfid_callback()
        last_rfid_check = time.ticks_ms()
    time.sleep(0.05)
