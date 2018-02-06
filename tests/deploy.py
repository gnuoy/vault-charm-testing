#!/usr/bin/env python3

import argparse
import logging
import os
import sys

from juju import loop
from juju.model import Model

import vault_tests

relations = {
    'mysql': {
        'vault_interface': 'shared-db',
        'db_interface': 'mysql:shared-db'},
    'postgresql': {
        'vault_interface': 'db',
        'db_interface': 'postgresql:db'}}
async def deploy(db, hamode):
    # Create a Model instance. We need to connect our Model to a Juju api
    # server before we can use it.
    model = Model()

    # Connect to the currently active Juju model
    await model.connect_current()
    print(hamode)
    #charm_dir = "{}/../{}".format(os.getcwd(), "build/builds/vault")
    charm_dir = "/home/liam/branches/vault-charm/build/builds/vault"
    try:
        # Deploy a single unit of the ubuntu charm, using the latest revision
        # from the stable channel of the Charm Store.
        if 'vault' in model.applications:
            vault_app = model.applications['vault']
        else:
            vault_app = await model.deploy(
              charm_dir,
              application_name='vault',
              series='xenial',
            )
        if db in model.applications:
            db_app = model.applications[db]
        else:
            db_app = await model.deploy(
              db,
              application_name=db,
              series='xenial',
            )
            relation = await vault_app.add_relation(
                relations[db]['vault_interface'],
                relations[db]['db_interface'],
            )

        if hamode and 'easyrsa' not in model.applications:
            easyrsa = await model.deploy(
              'cs:~containers/easyrsa',
              application_name='easyrsa',
              series='xenial',
            )
            etcd = await model.deploy(
              'etcd',
              application_name='etcd',
              series='xenial',
            )
            await etcd.set_config({'channel': '3.1/stable'})
            easyrsa_etcd = await etcd.add_relation(
                'certificates',
                'easyrsa:client',
            )
            vault_etcd = await etcd.add_relation(
                'db',
                'vault:etcd',
            )
            await vault_app.add_units(count=2)
        await vault_app.set_config({'disable-mlock': 'true'})
        await model.block_until(lambda: vault_app.status == 'active')
        await model.block_until(lambda: db_app.status == 'active')
        await model.block_until(lambda: model.all_units_idle() )
        vault_app = model.applications['vault']
        vault_units = [vault_app.units[0].public_address]
        if hamode:
            vault_units.extend([vault_app.units[1].public_address, vault_app.units[2].public_address])
        print("Run tests")          
        print(vault_units)
        vault_tests.run(units=vault_units)
        #vault_tests.run('http://{}:8201'.format(vault_app.units[0].public_address))
        #vault_tests.run('http://{}:8200'.format(vault_app.units[0].public_address))
    finally:
        # Disconnect from the api server and cleanup.
        await model.disconnect()

def main():
    logging.basicConfig(level=logging.INFO)

    # If you want to see everything sent over the wire, set this to DEBUG.
    ws_logger = logging.getLogger('websockets.protocol')
    ws_logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--database", choices=['mysql', 'postgresql'], help="Database backend", default='postgresql')
    parser.add_argument("--hamode", choices=['etcd', None], help="Database backend", default=None)
    args = parser.parse_args()
    
    # Run the deploy coroutine in an asyncio event loop, using a helper
    # that abstracts loop creation and teardown.
    loop.run(deploy(db=args.database, hamode=args.hamode))

if __name__ == '__main__':
    main()
