# ardu-pi-serial-cloud

### Control an arduino smart gardening prototype and push data on the cloud (via google cloud)


***ardu-pi-serial-cloud*** allows to connect and communicate with an arduino via serial port (e.g., tty_ACM0) and a simple protocol. The received data is then pushed to google cloud. 

Main functions:

* **serial_send_and_receive (ser,input)**: sends a single char to the arduino (available commands are defined via *Command(Enum)*), then it returns the received response.

* **read_arduino_sensors (ser)**: reads the sensor reading and decodes it with following syntax: *"S m:%d l:%d t:%d h:%d"* with m=moisture; l=light_intensity; t=temperature; h=humidity.

* **pubish(client, mqtt_topic, device, moist, light, humi, temp, status)**: publish the received information to the Google Cloud Iot Core via the MQTT protocol.

Example of invocation:

` python3 -u ardu-pi-serial-ext.py --project_id YOUR_PROJECT_ID --registry_id YOUR_REGISTRY_ID --device_id YOUR_DEVICE_ID --private_key_file rsa_private.pem --algorithm RS256 --cloud_region europe-west1 --ca_certs roots.pem --message_type event --device_type pi`

It is strongly suggested to create a symlink to the serial port of the arduino in order to avoid disconnections.


Under `/etc/udev/rules.d` create a rule `99-usb-serial.rules` and add the following line:
`#USB/Serial for Arduino
SUBSYSTEM=="tty", ATTRS{idVendor}=="XXX", ATTRS{idProduct}=="XXX", ATTRS{serial}=="XXX", SYMLINK+="tty_arduino"`

The values for *idVendor*, *idProduct*, and *serial* can be checked via `udevadm info -a -n /dev/ttyACMX`
