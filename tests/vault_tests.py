#!/usr/bin/env python3

import os
import hvac
import time
import requests
import urllib3
import uuid
import yaml


def get_client(vault_url):
    return hvac.Client(url=vault_url)


def init_vault(client, shares=1, threshold=1):
    return client.initialize(shares, threshold)


def get_clients(units):
    clients = []
    for unit in units:
        print("Creating client for {}".format(unit))
        vault_url = 'http://{}:8200'.format(unit)
        print(vault_url)
        clients.append((unit, get_client(vault_url)))
    return clients


def is_initialized(client):
    initialized = False
    print("Checking if vault is initialized")
    for i in range(1, 10):
        try:
            initialized = client[1].is_initialized()
        except (ConnectionRefusedError, urllib3.exceptions.NewConnectionError,
                urllib3.exceptions.MaxRetryError,
                requests.exceptions.ConnectionError):
            print("{} / 10".format(i))
            time.sleep(2)
        else:
            break
    else:
        raise Exception("Cannot connect")
    return initialized


def get_credentails(auth_file):
    print("Reading credentails from disk")
    with open(auth_file, 'r') as stream:
        vault_creds = yaml.load(stream)
    return vault_creds


def write_credentails(auth_file, vault_creds):
    with open(auth_file, 'w') as outfile:
        yaml.dump(vault_creds, outfile, default_flow_style=False)


def unseal_all(clients, key):
    for (addr, client) in clients:
        if client.is_sealed():
            print("Unsealing {}".format(addr))
            client.unseal(key)
    return clients


def auth_all(clients, token):
    for (addr, client) in clients:
        client.token = token
    return clients


def check_authenticated(clients):
    for (addr, client) in clients:
        for i in range(1, 10):
            try:
                assert client.is_authenticated()
            except hvac.exceptions.InternalServerError:
                print("{} / 10".format(i))
                time.sleep(2)
            else:
                break
        else:
            raise hvac.exceptions.InternalServerError


def check_read(clients, key, value):
    for (addr, client) in clients:
        print("    {} reading secret".format(addr))
        assert client.read('secret/uuids')['data']['uuid'] == value


def check_read_write(clients):
    key = 'secret/uuids'
    for (addr, client) in clients:
        value = str(uuid.uuid1())
        print("{} writing a secret".format(addr))
        client.write(key, uuid=value, lease='1h')
        # Now check all clients read the same value back
        check_read(clients, key, value)


def check_vault_ha_statuses(clients):
    print("Checking HA stauses")
    leader = []
    leader_address = []
    leader_cluster_address = []
    for (addr, client) in clients:
        assert client.ha_status['ha_enabled']
        leader_address.append(
            client.ha_status['leader_address'])
        leader_cluster_address.append(
            client.ha_status['leader_cluster_address'])
        if client.ha_status['is_self']:
            leader.append(addr)
            print("    {} is leader".format(addr))
        else:
            print("    {} is standby".format(addr))
    # Check there is exactly one leader
    assert len(leader) == 1
    # Check both cluster addresses match accross the cluster
    assert len(set(leader_address)) == 1
    assert len(set(leader_cluster_address)) == 1


def check_vault_status(clients):
    for (addr, client) in clients:
        assert not client.seal_status['sealed']
        assert client.seal_status['cluster_name']


def check_vault_statuses(clients):
    check_vault_status(clients)
    if len(clients) > 1:
        check_vault_ha_statuses(clients)


def run(units):
    clients = get_clients(units)
    auth_file = "{}/tests/data.yaml".format(os.getcwd())
    unseal_client = clients[0]
    print("Picked {} for performing unseal".format(unseal_client[0]))
    initialized = is_initialized(unseal_client)
    if initialized:
        vault_creds = get_credentails(auth_file)
    else:
        print("Initializing vault")
        vault_creds = init_vault(unseal_client[1])
        write_credentails(auth_file, vault_creds)
    keys = vault_creds['keys']
    clients = unseal_all(clients, keys[0])
    clients = auth_all(clients, vault_creds['root_token'])
    check_vault_statuses(clients)
    check_authenticated(clients)
    check_read_write(clients)
