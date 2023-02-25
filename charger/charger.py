#!/usr/bin/env python

# Name: 		charger.py
# Purpose:	Present a solar charger to VenusOS using values read from a Midnite Classic with a Whizbang Jr
# Date:		23-02-2023
# Version:	1.0
# Author:	Jan Bakuwel / YSolar NZ Ltd
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
from dbusdummyservice import DbusDummyService
from logger import setup_logging

MIDNITE_IP			= "192.168.1.101"
MIDNITE_TIMEOUT	= 10
MQTT_ENABLED		= False
MQTT_IP				= "192.168.1.100"
MQTT_TOPIC			= "midnite"
VERSION				= "v1.0"

MIDNITE_VICTRON = {
	0:		0,	# Midnite Resting:	Victron Off
	3:		4,	# Midnite Absorb:		Victron Absorption
	4:		3,	# Midnite BulkMPPT:	Victron Bulk
	5:		5,	# Midnite Float:		Victron Float
	6:		5,	# Midnite FloatMPPT:	Victron Float
	7:		7,	# Midnite Equalize:	Victron Equalize
	10:	3,	# HyperVOC:				Victron Bulk - I guess
	18:	7,	# EqualizeMPPT:		Victron Equalize
}

def twos_complement (uValue, iBits):
	if (uValue & (1 << (iBits - 1))) != 0:		# If sign bit is set
		uValue = uValue - (1 << iBits)			# then compute negative value
	#end if
	return uValue
#end twos_complement

class readMidnite ():

	def __init__ (self, sIP, iFrequency, Service):
		self.sIP				= sIP
		self.iFrequency   = iFrequency
		self.service		= Service
		self.classic		= ModbusClient (self.sIP, port=502)
		self.terminated	= False
		self.service._dbusservice['/Mgmt/ProcessVersion']				= VERSION
		#self.service._dbusservice['/Link/NetworkMode']					= None
		#self.service._dbusservice['/Link/NetworkStatus']				= None
		#self.service._dbusservice['/Link/ChargeVoltage']				= None
		#self.service._dbusservice['/Link/ChargeCurrent']				= None
		#self.service._dbusservice['/Settings/ChargeCurrentLimit']	= 70
		self.service._dbusservice['/Settings/BmsPresent']				= False
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
				CHARGE_STATE	= (HR41.registers[19] & 0xFF00)>> 8
				MIDNITE_STATE	= (HR41.registers[19] & 0x00FF)
				SHUNT_A			= float (twos_complement(HR43.registers[70],16))/10

				#logger.info ('Updating: State=%d, V=%f, A=%f, T=%f, CV=%f, CA=%f' % (242, PV_V, PV_A, BATT_T, BATT_V, BATT_A))
				self.service._dbusservice['/State']					= MIDNITE_VICTRON[CHARGE_STATE]
				self.service._dbusservice['/Pv/V']					= PV_V
				self.service._dbusservice['/Pv/I']					= PV_A
				self.service._dbusservice['/Dc/0/Voltage']		= BATT_V
				self.service._dbusservice['/Dc/0/Current']		= BATT_A
				self.service._dbusservice['/Yield/Power']			= round (PV_V * PV_A)
				self.service._dbusservice['/Connected']			= True
			else:
				logger.info ('unable to connect to %s' % self.sIP)
				self.service._dbusservice['/Connected']			= False
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
    servicename='com.victronenergy.solarcharger.net',
    deviceinstance=0,
    paths={
		'/State':								{'initial': 0},
		'/Pv/V':									{'initial': 0},
		'/Pv/I':									{'initial': 0},
		'/Dc/0/Voltage':						{'initial': 0},
		'/Dc/0/Current':						{'initial': 0},
		#'/Dc/0/Temperature':				{'initial': 0},
		#'/Link/NetworkMode': 				{'initial': None},
		#'/Link/NetworkStatus':				{'initial': None},
		#'/Link/ChargeVoltage':				{'initial': None},
		#'/Link/ChargeCurrent':				{'initial': None},
		#'/Settings/ChargeCurrentLimit':	{'initial': 70},
		'/Settings/BmsPresent':				{'initial': None},
		'/Yield/Power':						{'initial': None},
    },
    productname='Midnite Solar Charger',
    connection='dbus')

t = readMidnite (MIDNITE_IP, MIDNITE_TIMEOUT, b)
t.run ()
logger.info('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')
mainloop = GLib.MainLoop()
mainloop.run()
