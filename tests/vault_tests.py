#!/usr/bin/env python3

import os
import hvac
import time
import uuid
import yaml

def get_client(vault_url):
    return  hvac.Client(url=vault_url)

def init_vault(client, shares=1, threshold=1):
    return client.initialize(shares, threshold)

def run(units):
    clients = []
    for unit in units: 
        print("Creating client for {}".format(unit))
        vault_url = 'http://{}:8200'.format(unit)
        print("    {}".format(vault_url))
        clients.append((unit, get_client(vault_url)))
    print(os.getcwd())
    auth_file = "{}/tests/data.yaml".format(os.getcwd())
    unseal_client = clients[0]
    print("Picked {} for performing unseal".format(unseal_client[0]))
    initialized = False
    for i in range(1, 10):
        try:
            initialized = unseal_client[1].is_initialized()
        except:
            print("{} / 10".format(i))
            time.sleep(2)
        else:
            break
    else:
        raise Exception("Cannot connect")
    if initialized:
        print("Vault already initialized reading creds from disk")
        with open(auth_file, 'r') as stream:
            vault_creds = yaml.load(stream)
    else:
        print("Initializing vault")
        vault_creds = init_vault(unseal_client[1])
        with open(auth_file, 'w') as outfile:
            yaml.dump(vault_creds, outfile, default_flow_style=False)
    keys = vault_creds['keys']
    for _client in clients:
        print("Checking client {} is attatched to an unsealed unit".format(_client[0]))
        if _client[1].is_sealed():
            print("Unsealing {}".format(_client[0]))
            _client[1].unseal(keys[0])
        _client[1].token = vault_creds['root_token']
        print("Checking {} is authenticated".format(_client[0]))
        for i in range(1, 10):
            try: 
                assert _client[1].is_authenticated()
            except hvac.exceptions.InternalServerError:
                print("{} / 10".format(i))
                time.sleep(2)
            else:
                break
        else:
            raise hvac.exceptions.InternalServerError
        print("Reading and writing a secret")
        secret_uuid = str(uuid.uuid1())
        _client[1].write('secret/uuids', uuid=secret_uuid, lease='1h')
        assert _client[1].read('secret/uuids')['data']['uuid'] == secret_uuid
