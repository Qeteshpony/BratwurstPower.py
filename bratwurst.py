import json
import smbus3
import ina219
import logging
import time
import pca9557
import paho.mqtt.client as mqtt
import socket
import signal
import configparser
import os

hostname = socket.gethostname()

# check if ini file is available
if os.path.isfile("./bratwurstpower.ini"):
    inifile = "./bratwurstpower.ini"
elif os.path.isfile("/etc/bratwurstpower.ini"):
    inifile = "/etc/bratwurstpower.ini"
else:
    raise FileNotFoundError("Could not find bratwurstpower.ini")

# read config ini
config = configparser.ConfigParser()
config.read(inifile)

# import variables from config
mqtt_enabled = int(config["mqtt"]["enabled"])
mqtt_server = config["mqtt"]["server"]
mqtt_port = int(config["mqtt"]["port"])
mqtt_username = config["mqtt"]["username"]
mqtt_password = config["mqtt"]["password"]
mqtt_topic = config["mqtt"]["base_topic"] + hostname + "/"
hass_discovery_prefix = config["mqtt"]["hass_discovery_prefix"]
hardware_version = "2.1.0"
software_version = "0.1.0"
inainterval = float(config["general"]["measurement_interval"])
loglevel = config["general"]["loglevel"]
runtime_dir = config["general"]["runtime_directory"]

logging.basicConfig(level=loglevel,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# configuration of the INA219 ICs
inaconfig = {
    "Raspi": {
        "address": 0x40,
        "shunt": 0.01,
        "maxamp": 3.0,
        "maxvolt": 6.0,
    },
    "USB1": {
        "address": 0x41,
        "shunt": 0.01,
        "maxamp": 3.0,
        "maxvolt": 6.0,
    },
    "USB2": {
        "address": 0x42,
        "shunt": 0.01,
        "maxamp": 3.0,
        "maxvolt": 6.0,
    },
    "EXT": {
        "address": 0x43,
        "shunt": 0.01,
        "maxamp": 3.0,
        "maxvolt": 6.0,
    },
    "Input": {
        "address": 0x44,
        "shunt": 0.01,
        "maxamp": 5.0,
        "maxvolt": 17.0,
    },
}

pcapins = {
    "LED": {
        "pin": 0,
    },
    "IO1": {
        "pin": 1,
    },
    "IO2": {
        "pin": 2,
    },
    "IO3": {
        "pin": 3,
    },
    "IO4": {
        "pin": 4,
    },
    "USB2": {
        "pin": 5,
    },
    "USB1": {
        "pin": 6,
    },
    "EXT": {
        "pin": 7,
    },
}

# set default values to None
for pin in pcapins:
    pcapins[pin]["value"] = None
    pcapins[pin]["direction"] = None
    pcapins[pin]["state"] = "default"

# Address for the PCA9557 IO Expander
PCA9557_ADDRESS = 0x1F

logging.debug("Initialize I2C Bus")
i2c = smbus3.SMBus(1)
pca = pca9557.PCA9557(i2c, address=PCA9557_ADDRESS)

shutdown = False

inas = {}
for inaname, values in inaconfig.items():
    device = ina219.INA219(shunt_ohms=values["shunt"],
                           bus=i2c,
                           address=values["address"],
                           max_expected_amps=values["maxamp"],
                           log_level=loglevel)
    device.configure(voltage_range=device.RANGE_16V if values["maxvolt"] <= 16.0 else device.RANGE_32V,
                     gain=device.GAIN_AUTO)
    inas[inaname] = device


def signal_handler(sig, _frame):
    logging.info(f"Received signal: {sig}")
    global shutdown
    shutdown = True


def read_inas() -> dict:
    # Read values from all INA219 and return them as a dictionary
    results = {}
    for name, inaobj in inas.items():
        voltage = round(inaobj.voltage(), 2)
        if voltage > 1.0:
            results[name] = {
                "voltage": round(inaobj.voltage(), 2),
                "current": round(inaobj.current(), 1),
                "power": round(inaobj.power(), 0) / 1000,
                "shunt_voltage": round(inaobj.shunt_voltage(), 3),
            }
        else:
            results[name] = {
                "voltage": 0.0,
                "current": 0,
                "power": 0,
                "shunt_voltage": 0.0,
            }
    return results

def mqtt_on_connect(client: mqtt.Client, _userdata, _flags, _reason_code, _properties) -> None:
    # gets called when MQTT is connected
    logging.info("Connected to MQTT")
    client.subscribe(mqtt_topic + "command")
    client.publish(mqtt_topic + "status", "online", retain=True)
    hass_discovery(client)


def mqtt_on_message(_client: mqtt.Client, _userdata, msg: mqtt.MQTTMessage) -> None:
    # gets called when an MQTT message is received
    logging.info(f"MQTT message received on {msg.topic}: {msg.payload.decode()}")
    try:
        command = json.loads(msg.payload)
    except json.JSONDecodeError:
        logging.error(f"Command does not contain valid JSON: {msg.payload}")
    else:
        for key, value in command.items():
            if key in pcapins.keys():
                value = str(value)
                pinname = pcapins[key]["pin"]
                v = pcapins[key].get("value")
                d = pcapins[key].get("direction")
                s = pcapins[key].get("state")
                if value.lower() in ["0", "off", "false"]:
                    logging.info(f"Forcing {key} to off")
                    v = pca.value(pinname, 0)
                    d = pca.direction(pinname, pca.DIR_OUT)
                    s = "off"
                elif value.lower() in ["1", "on", "true"]:
                    logging.info(f"Forcing {key} to on")
                    v = pca.value(pinname, 1)
                    d = pca.direction(pinname, pca.DIR_OUT)
                    s = "on"
                elif value.lower() in ["-1", "release", "default"]:
                    logging.info(f"Releasing {key} to default state")
                    d = pca.direction(pinname, pca.DIR_IN)
                    s = "default"
                else:
                    logging.error(f"Invalid command received for {key}: {value}")
                pcapins[key]["value"] = v
                pcapins[key]["direction"] = d
                pcapins[key]["state"] = s
            else:
                logging.error(f"Invalid name received: {key}")

def hass_discovery(client: mqtt.Client) -> None:
    logging.info("Sending HASS Discovery Messages")
    deviceconfig = {
        "ids": [
            "bratwurst_power_"+hostname,
        ],
        "name": "Bratwurst Power " + hostname,
        "mf": "Qetesh",
        "mdl": "Bratwurst Power",
        "mdl_id": "Bratwurst Power" + hostname,
        "hw": hardware_version,
        "sw": software_version,
    }
    deviceconfig_short = {
        "ids": [
            "bratwurst_power_" + hostname,
        ],
    }
    originconfig = {
        "name": "Bratwurst Power " + hostname,
        "url": "https://qete.sh/gh/BratwurstPower.py"
    }
    first = True
    for pinname in pcapins.keys():
        pinjson = {
            "name": pinname,
            "stat_t": mqtt_topic + "pinstates",
            "cmd_t": mqtt_topic + "command",
            "val_tpl": "{{ value_json." + pinname + ".state }}",
            "cmd_tpl": "{\""+pinname+"\": \"{{ value }}\" }",
            "uniq_id": "bwpow_" + hostname + "_" + pinname,
            "ops": ["on", "off", "default"],
            "ic": "mdi:electric-switch",
            "avty_t": mqtt_topic + "status",
            "dev": deviceconfig if first else deviceconfig_short,
            "o": originconfig,
        }
        logging.debug(f"Sending HASS Discovery for Pin {pinname}")
        client.publish(
            hass_discovery_prefix + "select/bratwurst_power_" + hostname + "/" + pinname + "/config",
            json.dumps(pinjson),
            retain=True
        )
        first = False
    for name in inas.keys():
        voltagejson = {
            "name": name + " Voltage",
            "stat_t": mqtt_topic + "powerstats",
            "val_tpl": "{{ value_json." + name + ".voltage | float}}",
            "uniq_id": "bwpow_" + hostname + "_" + name + "_voltage",
            "dev_cla": "voltage",
            "unit_of_meas": "V",
            "avty_t": mqtt_topic + "status",
            "dev": deviceconfig_short,
            "o": originconfig,
        }
        currentjson = {
            "name": name + " Current",
            "stat_t": mqtt_topic + "powerstats",
            "val_tpl": "{{ value_json." + name + ".current | float}}",
            "uniq_id": "bwpow_" + hostname + "_" + name + "_current",
            "dev_cla": "current",
            "unit_of_meas": "mA",
            "avty_t": mqtt_topic + "status",
            "dev": deviceconfig_short,
            "o": originconfig,
        }
        powerjson = {
            "name": name + " Power",
            "stat_t": mqtt_topic + "powerstats",
            "val_tpl": "{{ value_json." + name + ".power | float}}",
            "uniq_id": "bwpow_" + hostname + "_" + name + "_power",
            "dev_cla": "power",
            "unit_of_meas": "W",
            "avty_t": mqtt_topic + "status",
            "dev": deviceconfig_short,
            "o": originconfig,
        }
        shuntjson = {
            "name": name + " Shunt Voltage",
            "stat_t": mqtt_topic + "powerstats",
            "val_tpl": "{{ value_json." + name + ".shunt_voltage | float}}",
            "uniq_id": "bwpow_" + hostname + "_" + name + "_shunt_voltage",
            "dev_cla": "voltage",
            "unit_of_meas": "mV",
            "icon": "mdi:resistor",
            "avty_t": mqtt_topic + "status",
            "dev": deviceconfig_short,
            "o": originconfig,
        }
        logging.debug(f"Sending HASS Discovery for {name} Voltage")
        client.publish(
            hass_discovery_prefix + "sensor/bratwurst_power_" + hostname + "/" + name + "_voltage/config",
            json.dumps(voltagejson),
            retain=True
        )
        logging.debug(f"Sending HASS Discovery for {name} Current")
        client.publish(
            hass_discovery_prefix + "sensor/bratwurst_power_" + hostname + "/" + name + "_current/config",
            json.dumps(currentjson),
            retain=True
        )
        logging.debug(f"Sending HASS Discovery for {name} Power")
        client.publish(
            hass_discovery_prefix + "sensor/bratwurst_power_" + hostname + "/" + name + "_power/config",
            json.dumps(powerjson),
            retain=True
        )
        logging.debug(f"Sending HASS Discovery for {name} Shunt Voltage")
        client.publish(
            hass_discovery_prefix + "sensor/bratwurst_power_" + hostname + "/" + name + "_shunt_voltage/config",
            json.dumps(shuntjson),
            retain=True
        )

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqttc.username_pw_set(mqtt_username, mqtt_password)
    mqttc.on_connect = mqtt_on_connect
    mqttc.on_message = mqtt_on_message
    mqttc.will_set(mqtt_topic + "status", "offline", retain=True)
    if mqtt_enabled:
        logging.info("Starting MQTT client")
        mqttc.connect(mqtt_server, mqtt_port, 60)
        mqttc.loop_start()

    lastchecktime = 0
    # loop until told otherwise...
    try:
        while shutdown is False:
            if lastchecktime + inainterval < time.time():
                lastchecktime = time.time()
                powerstats = read_inas()
                if mqttc.is_connected():
                    mqttc.publish(mqtt_topic + "powerstats", json.dumps(powerstats))
                    mqttc.publish(mqtt_topic + "pinstates", json.dumps(pcapins))
                if os.path.isdir(runtime_dir):
                    with open(os.path.join(runtime_dir, "powerstats.json"), "w") as f:
                        f.write(json.dumps(powerstats))
            # sleep for 100ms to prevent unnessecary cpu load
            time.sleep(0.1)
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received, shutting down")
    if mqttc.is_connected():
        logging.info("Shutting down MQTT client")
        mqttc.disconnect()
    exit(0)

if __name__ == '__main__':
    main()
