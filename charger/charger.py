#!/usr/bin/env python

# Name: 		charger.py
# Purpose:	Present a solar charger to VenusOS using values read from a Midnite Classic with a Whizbang Jr
# Date:		12-12-2024
# Version:	2.0
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

# VenusOS packages
sys.path.insert (1, os.path.join (os.path.dirname( __file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService
from logger import setup_logging

import config


def twos_complement (uValue, iBits):
	if (uValue & (1 << (iBits - 1))) != 0:		# If sign bit is set
		uValue = uValue - (1 << iBits)			# then compute negative value
	#end if
	return uValue
#end twos_complement

class readMidnite ():

	def __init__ (self, sIP, iFrequency):
		self.sIP				= sIP
		self.iFrequency   = iFrequency
		self.classic		= ModbusClient (self.sIP, port=502)
		self.terminated	= False

		logger.info ('Initialising Midnite thread: IP=%s, Freq=%d' % (self.sIP, self.iFrequency))
		self.service = VeDbusService (servicename='com.victronenergy.solarcharger.midnite', register=False)
		self.service.add_path('/DeviceInstance',			0)
		self.service.add_path('/ProductName',				'Midnite Classic Solar Charger')
		self.service.add_path('/Mgmt/ProcessName',		'charger.py')
		self.service.add_path('/Mgmt/ProcessVersion',	config.VERSION)
		self.service.add_path('/Mgmt/Connection',			'dbus')
		self.service.add_path('/FirmwareVersion',			config.VERSION)
		self.service.add_path('/HardwareVersion',			config.VERSION)
		self.service.add_path('/State',						None, writeable=True)
		self.service.add_path('/Pv/V',						None, writeable=True, gettextcallback=lambda a, x: "{:.0f}V".format(x))
		self.service.add_path('/Pv/I',						None, writeable=True, gettextcallback=lambda a, x: "{:.1f}A".format(x))
		self.service.add_path('/Yield/Power',				None, writeable=True, gettextcallback=lambda a, x: "{:.0f}W".format(x))
		self.service.add_path('/Dc/0/Voltage',				None, writeable=True, gettextcallback=lambda a, x: "{:.1f}V".format(x))
		self.service.add_path('/Dc/0/Current',				None, writeable=True, gettextcallback=lambda a, x: "{:.1f}A".format(x))
		self.service.add_path('/Connected',					1)
		self.service.register()
		logger.info ('Initialised Midnite thread: IP=%s, Freq=%d' % (self.sIP, self.iFrequency))
	#end __init__

	def readModbus (self):
		try:
			if self.classic.connect ():
				HR41 = self.classic.read_holding_registers (4100, 100)
				HR42 = self.classic.read_holding_registers (4200, 100)
				HR43 = self.classic.read_holding_registers (4300, 100)
				self.classic.close ()
				self.service['/Connected'] = 1

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

				#logger.info ('Updating: State=%d, V=%f, A=%f, T=%f, CV=%f, CA=%f' % (config.MIDNITE_VICTRON[CHARGE_STATE], PV_V, PV_A, BATT_T, BATT_V, BATT_A))
				self.service['/State']				= config.MIDNITE_VICTRON[CHARGE_STATE]
				self.service['/Pv/V']				= PV_V
				self.service['/Pv/I']				= PV_A
				self.service['/Yield/Power']		= round (PV_V * PV_A)
				self.service['/Dc/0/Voltage']		= BATT_V
				self.service['/Dc/0/Current']		= BATT_A
			else:
				logger.info ('unable to connect to %s' % self.sIP)
				self.service['/Connected'] = 0
			#end if
		except Exception as e:
			logger.info('Exception updating values: ' + repr(e))
			self.service['/Connected'] = 0
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
DBusGMainLoop (set_as_default=True)
t = readMidnite (config.MIDNITE_IP, config.MIDNITE_INTERVAL)
t.run ()

logger.info('Connected to dbus, and switching over to GLib.MainLoop() (= event based)')
mainloop = GLib.MainLoop()
mainloop.run()

