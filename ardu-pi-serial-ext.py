import argparse
import datetime
import json
import os
import sys
import platform
import random
import ssl
from time import sleep
import jwt
import paho.mqtt.client as mqtt
from rfc3339 import rfc3339
from enum import Enum
from socket import gaierror
from timeloop import Timeloop
from datetime import timedelta
import logging

""" First we define a set of constants for our program """
#MOIST_THRESHOLD = 40
#IRRIGATION_DURATION = 60 #seconds
#IRRIGATION_INTV = 3600 #seconds
SENSOR_READ_INTV = 3600 #seconds

"""global initialization """
jwt_iat = datetime.datetime.utcnow()
jwt_exp_mins = 60
client = None
mqtt_toic = ""
args = object()
device = "pi"
tl = Timeloop()
ser= None
logger = None

# Default starting values for simulated sensor readings
#light = 24
#moist = 15
#temp = 21
#humi = 30

""" These are the commands to pass to the Arduino via serial """
class Command(Enum):
  READ_SENSORS = 0
  START_PUMP   = 1
  STOP_PUMP    = 2

def parse_command_line_args():
  """Parse command line arguments."""
  parser = argparse.ArgumentParser(description=(
    'Google Cloud IoT Core MQTT device connection code.'))
  parser.add_argument(
    '--project_id',
    default=os.environ.get('GOOGLE_CLOUD_PROJECT'),
    help='GCP cloud project name')
  parser.add_argument(
    '--registry_id', required=True, help='Cloud IoT Core registry id')
  parser.add_argument(
    '--device_id', required=True, help='Cloud IoT Core device id')
  parser.add_argument(
    '--private_key_file',
    help='Path to private key file.')
  parser.add_argument(
    '--algorithm',
    choices=('RS256', 'ES256'),
    default='RS256',
    help='Which encryption algorithm to use to generate the JWT.')
  parser.add_argument(
    '--cloud_region', default='europe-west1', help='GCP cloud region')
  parser.add_argument(
    '--ca_certs',
    default='roots.pem',
    help=('CA root from https://pki.google.com/roots.pem'))
  parser.add_argument(
    '--message_type',
    choices=('event', 'state'),
    default='event',
    help=('Indicates whether the message to be published is a '
          'telemetry event or a device state message.'))
  parser.add_argument(
    '--mqtt_bridge_hostname',
    default='mqtt.googleapis.com',
    help='MQTT bridge hostname.')
  parser.add_argument(
    '--mqtt_bridge_port',
    default=8883,
    type=int,
    help='MQTT bridge port.')
  parser.add_argument(
    '--jwt_expires_minutes',
    default=60,
    type=int,
    help=('Expiration time, in minutes, for JWT tokens.'))
  parser.add_argument(
    '--device_type',
    choices=('sim', 'pi'),
    default='sim',
    required=True,
    help='Type of device: sim|pi.')
  parser.add_argument(
    '--serial_port',
    default='/dev/tty_arduino',
    help='Serial port device connected to the Arduino.')
  parser.add_argument(
    '--sensor_activation_intv',
    default=3600,
    type=int,
    help='Interval in seconds between sensor readings.')
  return parser.parse_args()

def create_jwt(project_id, private_key_file, algorithm):
  """Creates a JWT (https://jwt.io) to establish an MQTT connection.
      Args:
       project_id: The cloud project ID this device belongs to
       private_key_file: A path to a file containing either an RSA256 or
               ES256 private key.
       algorithm: The encryption algorithm to use. Either 'RS256' or 'ES256'
      Returns:
          An MQTT generated from the given project_id and private key, which
          expires in 20 minutes. After 20 minutes, your client will be
          disconnected, and a new JWT will have to be generated.
      Raises:
          ValueError: If the private_key_file does not contain a known key.
      """

  token = {
    'iat': datetime.datetime.utcnow(),
    'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
    'aud': project_id
  }

  with open(private_key_file, 'r') as f:
    private_key = f.read()

  logger.info ('Creating JWT using {} from private key file {}'.format(
    algorithm, private_key_file))

  return jwt.encode(token, private_key, algorithm=algorithm)

def get_client(
  project_id, cloud_region, registry_id, device_id, private_key_file,
  algorithm, ca_certs, mqtt_bridge_hostname, mqtt_bridge_port):
  """Create our MQTT client. The client_id is a unique string that identifies
  this device. For Google Cloud IoT Core, it must be in the format below."""
  client = mqtt.Client(
    client_id=('projects/{}/locations/{}/registries/{}/devices/{}'
               .format(
                       project_id,
                       cloud_region,
                       registry_id,
                       device_id)))
  client.username_pw_set(
    username='unused',
    password=create_jwt(
            project_id, private_key_file, algorithm))
  client.tls_set(ca_certs=ca_certs, tls_version=ssl.PROTOCOL_TLSv1_2)
  client.on_connect = on_connect
  client.on_publish = on_publish
  client.on_disconnect = on_disconnect
  client.on_message = on_message
  """ we have to take care of errors in the client (DNS, etc) so that we loop until we don't have an exception"""
  while True:
    try:
      client.connect(mqtt_bridge_hostname, mqtt_bridge_port)
    except gaierror as e:
      logging.warning ('Gaierror {}.'.format(e))
      logging.warning ('Waiting 60 seconds before restarting')
      sleep(60)
      pass
    else:
      break

  mqtt_config_topic = '/devices/{}/config'.format(device_id)
  client.subscribe(mqtt_config_topic, qos=1)
  client.loop_start()
  return client

def error_str(rc):
  """Convert a Paho error to a human readable string."""
  return '{}: {}'.format(rc, mqtt.error_string(rc))

def on_connect(unused_client, unused_userdata, unused_flags, rc):
  """Callback for when a device connects."""
  logger.info ('gcp_on_connect: %s', error_str(rc))

def on_disconnect(unused_client, unused_userdata, rc):
  """Paho callback for when a device disconnects."""
  logger.info ('gcp_on_disconnect: %s', error_str(rc))

def on_publish(unused_client, unused_userdata, unused_mid):
  """Paho callback when a message is sent to the broker."""
  logger.info ('gcp_on_publish')

def on_message(unused_client, unused_userdata, message):
  """Callback when the device receives a message on a subscription."""
  payload = str(message.payload)
  logger.info ('Received message \'{}\' on topic \'{}\' with Qos {}'.format(
          payload, message.topic, str(message.qos)))

def publish(client,
            mqtt_topic,
            device,
            moist      = None,
            light      = None,
            humi       = None,
            temp       = None,
            status     = None):

  """Function to publish sensor data to Cloud IoT Core."""
  payload = {}
  payload['clientid'] = platform.uname()[1]
  if (moist):  payload['moisture'] = float('{:.2f}'.format(moist))
  if (light):  payload['lightIntensity'] = float('{:.2f}'.format(light))
  if (humi):   payload['humidity'] = float('{:.2f}'.format(humi))
  if (temp):   payload['temperature'] = float('{:.2f}'.format(temp))
  if (status): payload['irrigation'] = status

  payload['timestamp'] = rfc3339(datetime.datetime.now())
  json_payload = json.dumps(payload)
  logger.info('Publishing message on the cloud: {}'.format(json_payload))
  client.publish(mqtt_topic, json_payload, qos=0)
  return

def read_sensors(device, ser, moist, light, humi, temp):
  """Read sensors or simulate the readings."""
  try:
    if device == 'pi':
      moist, light, humi, temp = read_arduino_sensors(ser)
    else:
      moist = simulate_sensors(moist, 3, 0, 100)
      light = simulate_sensors(light, 3, 0, 100)
      humi  = simulate_sensors(humi, 6, 0, 100)
      temp  = simulate_sensors(temp, 3, 0, 40)
  except IOError:
    logger.error ('I/O Error while reading sensors')
  return moist, light, humi, temp

def read_arduino_sensors(ser):
  """Request and receive sensor readings from Arduino over serial."""
  s = {}
  response = serial_send_and_receive(ser, str(Command.READ_SENSORS.value))
  response = response.rstrip()
  logging.info ('Received from Arduino: {}'.format(response))
  if response[0] == 'S':
    pairs = response.split(' ')
    for pair in pairs:
      if pair == 'S':
        continue
      else:
        name, value = pair.split(':')
        s[name] = value
  else:
    logger.error ('Error getting Arduino sensor values over serial port')
    return 0

  moist = int(s['m'])
  light = int(s['l'])
  humi  = int(s['h'])
  temp  = int(s['t'])

  return moist, light, humi, temp

def write_sensors(device, ser, input):
  """ write data to the sensors to launch/stop the relay (pump) """
  if (not input in Command):
    logger.warning ('Wrong write command... cannot send to arduino !')
    return None
  try:
    if device == 'pi':
      serial_send_and_receive(ser, str(input.value))
      logger.info('Sending command to Arduino:' + str(input))

  except IOError:
    logger.error ('I/O Error, cannot start or stop the pump')
  return None

def serial_send_and_receive(ser, input):
  """Write string to serial connection and return any response."""
  ser.write(input.encode())
  while True:
    try:
      sleep(0.01)
      resp = ser.readline()
      if resp:
        return resp.decode()
    except:
      logger.error ('Error while writing on the serial connection')
      pass
  sleep(0.1)
  return 'E'

def simulate_sensors(prev, stdev, min, max):
  """Gaussian distribution for simulated sensor readings."""
  delta = random.gauss(0, stdev)
  new = prev + delta
  if new < min or new > max:
    new = prev - delta
  return new

def init_serial(serial_port):
  import serial
  logger.info ('Creating and flushing serial port, then rebooting Arduino..')
  ser = serial.Serial(serial_port)
  with ser:
    ser.setDTR(False)
    sleep(1)
    ser.flushInput()
    ser.setDTR(True)
  ser = serial.Serial(serial_port, 9600, timeout=0.1)
  logger.info ('Sleeping 3s..')
  sleep(3)
  return ser


"""@tl.job(interval=timedelta(hours=24))
def irrigation_job():
  check_jwt_expiration()
  logging.info ("-------------irrigation start -----------------")
  write_sensors(device, ser, Command.START_PUMP)
  publish(client, mqtt_topic, device, status="TRUE")
  sleep(IRRIGATION_DURATION)
  write_sensors(device, ser, Command.STOP_PUMP)
  publish(client, mqtt_topic, device, status="FALSE")
  logging.info ("-------------irrigation stop-------------------")
"""

@tl.job(interval=timedelta(seconds=SENSOR_READ_INTV))
def sensor_read_job():

  moist, light, humi, temp = 0, 0, 0, 0

  check_jwt_expiration()
  logger.info ("reading values from arduino")
  moist, light, humi, temp = read_sensors(device, ser, moist, light, humi, temp)
  logger.info ("pulishing values to gcp")
  publish(client, mqtt_topic, device, moist=moist, light=light, humi=humi, temp=temp)

def check_jwt_expiration():
  global args, jwt_iat, jwt_exp_mins, client

  seconds_since_issue = (datetime.datetime.utcnow() - jwt_iat).seconds
  if seconds_since_issue > 60 * (jwt_exp_mins - 2):
    logger.info ('Refreshing token after', seconds_since_issue,'s')
    client.loop_stop()
    jwt_iat = datetime.datetime.utcnow()
    client = get_client(
      args.project_id, args.cloud_region,
      args.registry_id, args.device_id, args.private_key_file,
      args.algorithm, args.ca_certs, args.mqtt_bridge_hostname,
      args.mqtt_bridge_port)

def main(argv):
  global logger, ser, args, mqtt_topic, SENSOR_READ_INTV, tl, device, jwt_iat, jwt_exp_mins, client

  logging.basicConfig(format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s', level=logging.INFO)
  logger = logging.getLogger("ardu-pi-serial-ext")

  args = parse_command_line_args()
  sub_topic = 'events' if args.message_type == 'event' else 'state'
  mqtt_topic = '/devices/{}/{}'.format(args.device_id, sub_topic)

  device = args.device_type
  if device == 'pi':
    ser = init_serial(args.serial_port)
  else:
    ser = None

  jwt_iat = datetime.datetime.utcnow()
  jwt_exp_mins = args.jwt_expires_minutes

  client = get_client(
    args.project_id, args.cloud_region, args.registry_id, args.device_id,
    args.private_key_file, args.algorithm, args.ca_certs,
    args.mqtt_bridge_hostname, args.mqtt_bridge_port)

  tl.start(block=True)

if __name__ == '__main__':
  main(sys.argv)
