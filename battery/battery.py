#!/usr/bin/env python

# Name: 		battery.py
# Purpose:	Present a battery monitor to VenusOS using values read from a Midnite Classic with a Whizbang Jr
# Date:		23-02-2023
# Version:	1.0
# Author:	Jan Bakuwel / YSolar NZ Ltd
# Based on:	/opt/victronenergy/dbus-systemcalc-py/scripts/dummybattery.py
# License:	GNU General Public License v3.0

from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
import argparse
import logging
import sys
import os
import time
from pymodbus.client.sync import ModbusTcpClient as ModbusClient

# our own packages
sys.path.insert (1, os.path.join (os.path.dirname( __file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
sys.path.insert (1, os.path.join (os.path.dirname( __file__), '/opt/victronenergy/dbus-mqtt'))
from dbusdummyservice import DbusDummyService
from logger import setup_logging
import paho.mqtt.client

MIDNITE_IP			= "192.168.1.101"
MIDNITE_TIMEOUT	= 10
MQTT_ENABLED		= False
MQTT_IP				= "192.168.1.100"
MQTT_TOPIC			= "midnite"
VERSION				= "v1.0"

def twos_complement (uValue, iBits):
	if (uValue & (1 << (iBits - 1))) != 0:		# If sign bit is set
		uValue = uValue - (1 << iBits)			# then compute negative value
	#end if
	return uValue
#end twos_complement

class readMidnite ():

	def __init__ (self, sIP, iFrequency, sMQTT, sTopic, Service):
		self.sIP				= sIP
		self.iFrequency   = iFrequency
		self.service		= Service
		self.classic		= ModbusClient (self.sIP, port=502)
		self.sMQTT			= sMQTT
		self.sTopic			= sTopic + '/'
		self.mqttClient	= paho.mqtt.client.Client = paho.mqtt.client.Client ()
		self.terminated	= False
		self.service._dbusservice['/Mgmt/ProcessVersion']	= VERSION
		logger.info ('Initialised Midnite thread: IP=%s, Freq=%d' % (self.sIP, self.iFrequency))
	#end __init__

	def readModbus (self):
		try:
			if self.classic.connect ():
				HR41 = self.classic.read_holding_registers (4100, 100)
				HR42 = self.classic.read_holding_registers (4200, 100)
				HR43 = self.classic.read_holding_registers (4300, 100)
				self.classic.close ()

				UNIT_ID			= HR41.registers[00]
				UNIT_SW_DATE_Y	= HR41.registers[1]
				UNIT_SW_DATE_M	= (HR41.registers[2] & 0xFF00) >> 8
				UNIT_SW_DATE_D	= (HR41.registers[2] & 0x00FF)

				SOC				= HR43.registers[72]
				PV_V				= float(HR41.registers[15])/10
				PV_A				= float(HR41.registers[20])/10
				BATT_V			= float(HR41.registers[14])/10
				BATT_A			= float(HR41.registers[16])/10
				BATT_P			= HR41.registers[18]
				BATT_T			= float(HR41.registers[31])/10
				FET_T				= float(HR41.registers[32])/10
				PCB_T				= float(HR41.registers[33])/10
				SHUNT_A			= float (twos_complement(HR43.registers[70],16))/10
				CHARGE_STATE	= (HR41.registers[19] & 0xFF00)>> 8
				MIDNITE_STATE	= (HR41.registers[19] & 0x00FF)

				#logger.info ('Updating: SOC=%d, V=%f, A=%f, P=%f, T=%f' % (SOC, BATT_V, SHUNT_A, (BATT_V*SHUNT_A), BATT_T))
				self.service._dbusservice['/Dc/0/Voltage']		= BATT_V
				self.service._dbusservice['/Dc/0/Current']		= SHUNT_A
				self.service._dbusservice['/Dc/0/Power']			= round (BATT_V * SHUNT_A)
				self.service._dbusservice['/Dc/0/Temperature']	= BATT_T
				self.service._dbusservice['/Soc']					= SOC
				self.service._dbusservice['/Connected']			= True
				if MQTT_ENABLED:
					if (self.mqttClient.connect (self.sMQTT) == 0):
						try:
							self.mqttClient.publish (self.sTopic + 'Voltage',		'{:0.2f}'.format (BATT_V),					retain = True)
							time.sleep (0.1)
							self.mqttClient.publish (self.sTopic + 'Current',		'{:0.2f}'.format (SHUNT_A),				retain = True)
							time.sleep (0.1)
							self.mqttClient.publish (self.sTopic + 'Power',			'{:0.2f}'.format (BATT_V * SHUNT_A),	retain = True)
							time.sleep (0.1)
							self.mqttClient.publish (self.sTopic + 'Temperature',	'{:0.1f}'.format (BATT_T),					retain = True)
							time.sleep (0.1)
							self.mqttClient.publish (self.sTopic + 'SOC',			'{:d}'.format (SOC),							retain = True)
						except Exception as e:
							log ('readModbus[{:s}]: {:s}'.format (self.sTopic, repr(e)))
						finally:
							self.mqttClient.disconnect ()
						#end try
					#end if
				#end if
			else:
				logger.info ('unable to connect to %s' % self.sIP)
				self.service._dbusservice['/Connected'] = False
			#end if
		except Exception as e:
			logger.info('Exception updating values: ' + repr(e))
		#end try
		return True
	#end readModbus

	def run (self):
		self.t = GLib.timeout_add (self.iFrequency*1000, self.readModbus)
	#end run

	def cancel (self):
		GLib.remove_source (self.t)
		self.terminated = True
	#end cancel

#end readMidnite

logger = setup_logging (debug=False)

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop (set_as_default=True)

b = DbusDummyService (
    servicename='com.victronenergy.battery.net',
    deviceinstance=0,
    paths={
			#'/TimeToGo':					{'initial': None},
			#'/CustomName':				{'initial': None},
			'/Soc':							{'initial': 20},
			'/Dc/0/Voltage':				{'initial': 0},
			'/Dc/0/Current':				{'initial': 0},
			'/Dc/0/Power':					{'initial': 0},
			'/Dc/0/Temperature':			{'initial': None}},
    productname='Midnite Battery Monitor',
    connection='dbus')

t = readMidnite (MIDNITE_IP, MIDNITE_TIMEOUT, MQTT_IP, MQTT_TOPIC, b)
t.run ()
logger.info ('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
mainloop = GLib.MainLoop()
mainloop.run()
