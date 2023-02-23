# Installation

1. Copy all files from this repository to the directory /data/classic on your VenusOS system

2. Edit battery.py and charger.py to update the constants:

```
MIDNITE_IP                      = <IP address of your Midnite Classic>
MIDNITE_INTERVAL        = <query interval in seconds>
MQTT_IP                         = <IP address of MQTT broker>
MQTT_TOPIC                      = <Topic to use for MQTT messages>
```

3. Add the following lines to your /data/rcS.local

```
cd /service
ln -s /data/classic/battery/service battery
ln -s /data/classic/charger/service charger
```

4. Reboot

5. Enjoy!
