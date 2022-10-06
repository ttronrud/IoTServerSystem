import sys
import socket
import requests
import json
import time

h_name = socket.gethostname()
LAN_IP = socket.gethostbyname(h_name)
api_port = "1234"
collection_port = "1337"

#Deposit some data to one of the system's collection servers
#Mimicking some individual component sending data to the mothership
deposit_url = "http://" + LAN_IP + ":" + collection_port + "/"
test_dat_str = '{"data":"DEPOSITED DATA"}'
test_dat_json = json.loads(test_dat_str)
response = requests.post(deposit_url, json = test_dat_json)
print(response)

#Leave time for the queue to be processed
time.sleep(1.0)

#POST to the API server mimicking some client requesting the
#accumulated data
url = "http://" + LAN_IP + ":" + api_port + "/path-to-some/CONFIG"
test_str = '{"txt":"TEST", "port":1337}'

test_json = json.loads(test_str)
response = requests.get(url, json=test_json)


print(response.text)