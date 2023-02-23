# Installation

1. Copy all files from this repository to the directory /data/classic on your VenusOS system

2. Edit battery.py and charger.py to update the constants (especially the IP address of your Midnite Classic)

3. Add the following lines to your /data/rcS.local

```
cd /service
ln -s /data/classic/battery/service battery
ln -s /data/classic/charger/service charger
```

4. Reboot

5. Enjoy!
