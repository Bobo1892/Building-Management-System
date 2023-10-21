import threading
import RPi.GPIO as GPIO
from datetime import datetime, timedelta, date
from time import sleep, strftime
import time
from urllib.request import urlopen, Request
#import urlibb
import urllib3
import json
from PCF8574 import PCF8574_GPIO
from Adafruit_LCD1602 import Adafruit_CharLCD
import Freenove_DHT as DHT

#import all necessary libraries used throughout writing/testing/running program


GPIO.setwarnings(False)	#warnings off
GPIO.setmode(GPIO.BOARD) #set to Board because easier to use


PIR_pin = 11
DHT_pin = 13
greenLED = 40
blueLED = 22
redLED = 12
dwbut = 32
bluebut = 38
redbut = 36	#all inputs and outputs on circuit board set to their respective GPIO board numbers based on hardware
lightstat = False
dwstat = True
dwupdate = False
hvacupdate = False
hvacmsg = 'OFF '
terminateprog = False
alarmstat = False
starttime = 0
elapsed =0
energy = 0
cost = 0.00
hvacflag = 0
humidity = None	
currTemp = 0
wantedTemp = 75	
fname = 'log.txt' #all global variables to be used throughout functions in the program


GPIO.setup(greenLED, GPIO.OUT)
GPIO.output(greenLED, False)
GPIO.setup(blueLED, GPIO.OUT)
GPIO.output(blueLED, False)
GPIO.setup(redLED, GPIO.OUT)
GPIO.output(redLED, False)
#set up LEDS as outputs and turn them off

GPIO.setup(dwbut, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(bluebut, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(redbut, GPIO.IN, pull_up_down=GPIO.PUD_UP)
#setup all buttons as input and set them as pull up resistors as to avoid random values

GPIO.setup(PIR_pin, GPIO.IN)
#set up PIR wire as input

dht = DHT.DHT(DHT_pin) #set dht with DHT module functino

PCF8574_address = 0x27  # I2C address of the PCF8574 chip.
PCF8574A_address = 0x3F  # I2C address of the PCF8574A chip.
# Create PCF8574 GPIO adapter.
try:
    mcp = PCF8574_GPIO(PCF8574_address)
except:
    try:
        mcp = PCF8574_GPIO(PCF8574A_address)
    except:
        print ('I2C Address Error !')
        exit(1)

# Create LCD, passing in MCP GPIO adapter.
lcd = Adafruit_CharLCD(0, 2, [4, 5, 6, 7], mcp)
mcp.output(3, 1) # Turns on lcd backlight
lcd.begin(16, 2) # Set lcd mode

#gest the humidity value from the CIMIS website with the API
def getHumidity(hr, curr):

	global humidity
	date_str = ''
	if((hr <= 0) or (curr.hour > time.localtime(time.time()).tm_hour)):
		date_str = datetime.strftime(curr - timedelta(days=1), '%Y-%m-%d')
	else:
		date_str = curr.strftime('%Y-%m-%d')
		
	req_url ='http://et.water.ca.gov/api/data?appKey=dd12d7ef-5472-4f25-9c5e-c274ac751792&targets=75&startDate='
	req_url += date_str
	req_url += '&endDate='
	req_url += date_str
	req_url += '&dataItems=hly-rel-hum'
	content = None
	data = None
	req = Request(req_url, headers={"Accept": "application/json"})
	try: 
		content = urlopen(req)
		assert(content is not None)
		
	except urllib.error.HTTPError as e:
		print('HTTP ERROR')
		msg = e.read()
		print(msg)
	except urllib.error.URLError:
		print('URL ERROR')
	except:
		print('REQUEST REJECTED')
	data = json.load(content)
	assert(data is not None)
	hly_data = data['Data']['Providers'][0]['Records']
	humidity = hly_data[hr - 1]['HlyRelHum']['Value']
	#finds current humidity
	while(humidity is None):
		hr -= 1
		if (hr > 0):
			humidity = hly_data[hr - 1]['HlyRelHum']['Value']
		else:
			getHumidity(hr, curr)
	print('CIMIS Humidity is: ', humidity) 

#flashes the LEDs when the fire alarm goes off
def alarmBlink():
	GPIO.output(greenLED, True)
	GPIO.output(redLED, True)
	GPIO.output(blueLED, True)
	sleep(0.5)
	GPIO.output(greenLED, False)
	GPIO.output(redLED, False)
	GPIO.output(blueLED, False)
	sleep(0.5)
	GPIO.output(greenLED, True)
	GPIO.output(redLED, True)
	GPIO.output(blueLED, True)
	sleep(0.5)
	GPIO.output(greenLED, False)
	GPIO.output(redLED, False)
	GPIO.output(blueLED, False)

# Check temperature difference
def check_temp():
	global hvacmsg
	global hvacupdate
	global currTemp
	global wantedTemp
	global dwstat
	global fname
	global alarmstat
	global starttime
	global elapsed
	global energy
	global cost
	global hvacflag
	old_msg = hvacmsg
	diff = currTemp - wantedTemp
	
    #turn on fire alarm if over 80 since 95 is too high
	if (currTemp > 80):
		alarmBlink()
		alarmstat = True
		#dw_status = False
	elif((diff <= -3) and dwstat):
		if hvacmsg != 'HEAT':
			hvacmsg = 'HEAT'
			hvacflag = 2
			starttime = time.time()
			GPIO.output(blueLED, False)
			GPIO.output(redLED, True) #turn on heater and turn on red LED to represent heater turning on
			hvacupdate = True
	elif((diff >= 3) and dwstat):
		if hvacmsg != 'AC  ':
			hvacmsg = 'AC  '
			starttime = time.time()
			hvacflag = 1
			GPIO.output(blueLED, True)
			GPIO.output(redLED, False) #turn on AC and turn on blue LED to represent ac turning on 
			hvacupdate = True
	else:
		if hvacmsg != 'OFF ':
			hvacmsg = 'OFF '
			elapsed = time.time() - starttime
			if (hvacflag == 1):
				energy = elapsed * 5 
			elif (hvacflag == 2):
				energy = elapsed * 10 #calculate energy based on which HVAC function was used
			energy = (energy / 1000)
			energy = round(energy, 2)
			cost = round((energy * 0.5), 2) #calculates cost from time
			print(f"Elapsed: {elapsed}, Energy: {energy}, Cost: {cost}")
			starttime = 0
			#energy = 0
			elapsed = 0 #set timers back to zero 
			#cost = 0
			hvacupdate = True
			GPIO.output(blueLED, False)
			GPIO.output(redLED, False)


#humidity thread function
def humthread():
	global humidity
	global terminateprog
	#curr = 0;
	init = True
	start_time = time.time()
	while(not terminateprog):
		if((init) or (time.time() - start_time >= 3600)):
			curr = datetime.now()
			hr = curr.hour
			getHumidity(hr, curr)
			init = False
		time.sleep(5)
	print('CIMIS thread end')

#gets the temp from the DHT sensor and calculates temp
def DHTthread(lock):
	global currTemp
	global wantedTemp
	global humidity
	global terminateprog
	t_init = True
	i = 0
	tempArr = [0, 0, 0]
	while(not terminateprog):
		for j in range (0, 15):
			chk = dht.readDHT11()
			if(chk is dht.DHTLIB_OK):
				break
			time.sleep(0.1)
		tempArr[i] = dht.temperature #adds temperature in array to be averaged if reading is ok
		if(i == 2):
			i = 0
		else:
			i += 1
		assert(humidity is not None)
		ind = (sum(tempArr) / 3.0) * 1.8 + 32.0 + 0.05 * float(humidity) #calculate weather index
		currTemp = int(ind)
		time.sleep(1)
	print('DHT Thread end')

#thread for PIR sensor
def PIRthread(lock):
	count = 0
	global lightstat
	global fname
	global terminateprog
	print('PIR Begin')
	while(not terminateprog):
		time.sleep(2)
		if(GPIO.input(PIR_pin) == GPIO.HIGH):
			count = 0
			GPIO.output(greenLED, True)
			old_status = lightstat
			lightstat = True
			print('MOVEMENT DETECTED') #turn on green LED if movement is detected from PIR and display message
		else:
			count += 1

		if(count == 5): #since it is updated once every other second, after count reaches 5, it will turn off the LED and make a statement for it
			GPIO.output(greenLED, False)
			old_status = lightstat
			lightstat = False
			print('NO MOVEMENT IN LAST 10 SEC')
			count = 0
	print('PIR ended')

#controls the LCD display when important messages need to be displayed on whole board
def lcdthread(lock):
	global mcp
	global lcd
	global hvacupdate
	global dwupdate
	global dwstat
	global currTemp
	global wantedTemp
	global lightstat
	global terminateprog
	global alarmstat
	
	old_status = lightstat
	old_des_t = wantedTemp
	while(not terminateprog):
		check_temp()
		if (dwupdate): #door/window open or closed
			lcd.clear()
			lcd.setCursor(0,0)
			if dwstat:
				lcd.message('DOOR/WINDOW SAFE\n')
				lcd.message('   HVAC RESUMED')
			else:
				lcd.message('DOOR/WINDOW OPEN\n')
				lcd.message('   HVAC HALTED') #update the LCD with the door/window status if it changes and then set the status to false
			dwupdate = False
			hvacupdate = False
			time.sleep(3)
			lcd.clear() #clear LCD back to normal after 3 sec
		if (alarmstat):
			lcd.clear()
			lcd.setCursor(0,0)
			lcd.message('FIRE ALARM\nDW OPEN EVACUATE')
			time.sleep(3)
			alarmstat = False
			lcd.clear #fire alarm situation
		elif hvacupdate:
			lcd.clear()
			lcd.setCursor(0,0)
			lcd.message('HVAC ')
			lcd.message(hvacmsg)
			if (hvacmsg == 'OFF '):
				lcd.message(f"COST:\n{energy}KWh, ${cost}") #display energy used and cost when hvac turns off
			hvacupdate = False
			time.sleep(3)
			lcd.clear()
		else:
			lcd_display()
			time.sleep(0.1)
	print('LCD Thread ended')

#handles when button is pressed
def butPress(pin):
	global wantedTemp
	global dwstat
	global dwupdate
	global fname
	#print('fn called')
	if(pin == dwbut): #if the button controlling doors/windows is pressed, update its status
		dwstat = not dwstat
		if dwstat:
			print('Door or window closed')
		else:
			print('Door or window open')
		dwupdate = True
		#if the current temperature is in an acceptable range, then change the desired temperature depending on which button was pressed
	elif(pin == bluebut):
		if(wantedTemp > 65):
			wantedTemp -= 1
	elif(pin == redbut):
		#print('redcalled')
		if(wantedTemp < 85):
			wantedTemp += 1

#lcd display during normal situation with parameters shown in assignment lcd display example
def lcd_display():
	global currTemp
	global wantedTemp
	global dwstat
	global hvacmsg
	global lightstat
	global lcd
	global alarmstat
	global energy
	global cost
	lcd.setCursor(0, 0)
	lcd.message(str(currTemp)+'/'+str(wantedTemp))
	lcd.message('   D:')
	if dwstat:
		lcd.message('SAFE \n')
	else:
		lcd.message('OPEN \n')
	lcd.message('H:')
	lcd.message(hvacmsg)
	lcd.message('    L:')
	if lightstat:
		lcd.message('ON ')
	else:
		lcd.message('OFF\n')
		#lcd.message(f"{energy}, KWh,  ${cost}")

# Button events detection calling butPress function
GPIO.add_event_detect(dwbut, GPIO.BOTH, callback=butPress, bouncetime=300)
GPIO.add_event_detect(redbut, GPIO.FALLING, callback=butPress, bouncetime=300)
GPIO.add_event_detect(bluebut, GPIO.BOTH, callback=butPress, bouncetime=300)


#main function, starts all the threads that are used and handles various cases for the program ending
if __name__ == '__main__':
	try: 
		print('Program start')
		lock = threading.Lock()
		curr = datetime.now()
		hr = curr.hour
		print('CIMIS Start')
		t0 = threading.Thread(target=humthread)
		t0.daemon = True
		t0.start()
		while(humidity is None):
			time.sleep(1)
		print('Initializing DHT Sensor')
		t1 = threading.Thread(target=DHTthread, args=(lock,))
		t1.daemon = True
		t1.start()
		print('Temperature calculating')
		time.sleep(5)
		t2 = threading.Thread(target=lcdthread, args=(lock,))
		t2.daemon = True
		t2.start()
		time.sleep(55)
		print('PIR Sensor Initializing')
		t3 = threading.Thread(target=PIRthread, args=(lock,))
		t3.daemon = True
		t3.start()
		msg = input('Exit with CTRL + C \n')
		terminateprog = True
		#t.join()
		t0.join()
		t1.join()
		t2.join()
		t3.join()
		mcp.output(3,0)
		lcd.clear()
		GPIO.cleanup()
		print('BMS ends')
	except KeyboardInterrupt:
		terminateprog = True
		#t.join()
		t0.join()
		t1.join()
		t2.join()
		t3.join()
		mcp.output(3,0)
		lcd.clear()
		GPIO.cleanup()
		print('BMS ends')
	except:
		terminateprog = True
		#t.join()
		t0.join()
		t1.join()
		t2.join()
		t3.join()
		mcp.output(3,0)
		lcd.clear()
		GPIO.cleanup()
		print('BMS ends')
