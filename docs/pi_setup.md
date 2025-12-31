**Step-by-step installation of rvc-monitor**
**and rvc2mqtt on a Raspberry Pi**
**(including Samba, Docker and Portainer)**

This is a "cheat sheet" for novices (like me) who need to configure this on a Raspberry Pi.  I recommend installing rvc-monitor in addition to rvc2mqtt.  You can use the logging feature in rvc2mqtt to turn on a dump of all the RVC to MQTT traffic that is generated.  But rvc-monitor provides another way to do it, along with visualization in MQTT explorer rather than via log files.

**Setup RPi**

| Item | Details |
| --- | --- |
| Download RPi imager | https://downloads.raspberrypi.com/imager/imager_latest.exe |
| Flash SSD using RPi software |  |
| Obtain IP address by looking at router |  |
| SSH into Rpi | SSH *username*@*192.168.xxx.xxx* |
| Get admin rights | sudo usermod -aG sudo *username* |

**Install CANBus utils and service**

| Item | Details |
| --- | --- |
| Modify config.txt with can info | sudo nano /boot/firmware/config.txt |
|  | dtparam=spi=on<br>dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25<br>dtoverlay=spi-bcm2835-overlay |
| Reboot | sudo reboot |
| Install can utils | sudo apt-get install can-utils |
| Update all | sudo apt update && sudo apt upgrade |
| Clean up | sudo apt autoremove |
| Bring can up | sudo /sbin/ip link set can0 up type can bitrate 250000 |
| Send test message | cansend can0 7DF#0201050000000000 |
| Create the Service File | sudo nano /etc/systemd/system/can0.service |
| Add the Following Content | [Unit]<br>Description=Setup SocketCAN interface can0 with a baudrate of 500000<br>After=<<!nav>>network.target<<!/nav>>  # Or the appropriate network service for your distribution<br>[Service]<br>Type=oneshot<br>RemainAfterExit=yes<br>ExecStartPre=/sbin/ip link set can0 type can bitrate 250000<br>ExecStart=/sbin/ip link set can0 up<br>ExecStop=/sbin/ip link set can0 down<br>[Install]<br>WantedBy=multi-user.target |
| Enable and Start the Service | sudo systemctl enable can0.service<br>sudo systemctl start can0.service |

**Install Samba for easy file copying Windows to RPi**

| Item | Details |
| --- | --- |
| Install Samba | sudo apt install samba |
| Create shared directory | mkdir Programs |
| Set rights | sudo chmod -R 0777 /home/*username*/Programs |
| Configure Samba | sudo nano /etc/samba/smb.conf |
| Modify [homes] section | [homes]<br>comment = Home Directories<br>browseable = yes<br>read only = no<br>valid users = %S<br>writable = yes<br>create mask = 0777<br>directory mask = 0777 |
| Create samba user | sudo smbpasswd -a *username* |
| Restart Samba Services | sudo systemctl restart smbd |

**Install MQTT broker**

| Item | Details |
| --- | --- |
| Install mosquitto | sudo apt install mosquitto |
| Enable Mosquitto to Start on Boot | sudo systemctl enable mosquitto.service |
| Check status | sudo systemctl status mosquitto |
| Configure Mosquitto | sudo nano /etc/mosquitto/mosquitto.conf |
|  | listener 1883<br>allow_anonymous true |
| Restart | sudo systemctl restart mosquitto.service |

**Install MQTT Explorer in Windows**

| Item | Details |
| --- | --- |
| Install MQTT Explorer | http://mqtt-explorer.com/ |

**Install Docker**

| Item | Details |
| --- | --- |
| Install Docker | curl -sSL https://get.docker.com | sh |
| Add User to Docker Group | sudo usermod -aG docker *username* |
| Refresh group | newgrp docker |
| Test | docker run hello-world |

**Install Portainer for easy Docker management**

| Item | Details |
| --- | --- |
| Create Portainer Volume | docker volume create portainer_data |
| Deploy Portainer Container | docker run -d -p 8000:8000 -p 9443:9443 \  <br> --name portainer \  <br> --restart=always \  <br> -v /var/run/docker.sock:/var/run/docker.sock \  <br> -v portainer_data:/data \  <br> portainer/portainer-ce:latest |
| Access Portainer | https://*192.168.xxx.xxx*:9443 |
| Set credentials |  |

**Install rvc-monitor to easily see all RVC traffic**

| Item | Details |
| --- | --- |
| Clone rvc-monitor from GitHub to Windows | From: https://github.com/nealcarney/rvc-monitor<br>To: C:\Users\\*username*\ Documents\Git\rvc-monitor |
| Copy rvc-monitor from Windows to RPi using Samba | From: C:\Users\\*username*\ Documents\Git\rvc-monitor<br>To: users\\*username*\Programs |
| Build docker image | docker build -t rvc-monitor . |
| Run docker| docker run -d --restart=always \  <br>  --name=rvc-monitor \  <br>  --net=host \  <br>  --device=/dev/can0 \  <br>  -e MQTT_BROKER=*192.168.xxx.xxx* \  <br>  -e MQTT_PORT=1883 \  <br>  rvc-monitor |

**Install rvc2mqtt for Home Assistant integration**

| Item | Details |
| --- | --- |
| Clone rvc2mqtt from GitHub to Windows | From: https://github.com/nealcarney/rvc2mqtt<br>To: C:\Users\\*username*\ Documents\Git\rvc2mqtt |
| Copy rvc2mqtt to RPi using Samba | From: C:\Users\\*username*\ Documents\Git\rvc2mqtt<br>To: users\\*username*\Programs |
| Build docker image | docker build -t rvc2mqtt . |
| Run docker<br>(delete username and password if<br> unless using Home Assistant MQTT broker) | docker run -d \  <br>  --restart=unless-stopped \  <br>  --name=rvc2mqtt \  <br>  --net=host \  <br>  --privileged \  <br>  --device=/dev/can0 \  <br>  -v /home/*username*/Programs/rvc2mqtt:/app:rw \  <br>  -e FLOORPLAN_FILE_1=/app/config/floorplan.yaml \  <br>  -e LOG_CONFIG_FILE=/app/config/log_config.yaml \  <br>  -e MQTT_HOST=*192.168.xxx.xxx* \  <br>  -e MQTT_PORT=1883 \  <br>  -e MQTT_USERNAME=XXXX \  <br>  -e MQTT_PASSWORD=XXXX \  <br>  rvc2mqtt |