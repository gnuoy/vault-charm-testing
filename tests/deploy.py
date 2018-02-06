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


async def deploy_vault_app(model, charm_dir, series='xenial'):
    if 'vault' in model.applications:
        vault_app = model.applications['vault']
    else:
        vault_app = await model.deploy(
            charm_dir,
            application_name='vault',
            series=series,
            config={'disable-mlock': 'true'},
        )
    return vault_app


async def deploy_db_app(model, db, series='xenial'):
    if db in model.applications:
        db_app = model.applications[db]
    else:
        db_app = await model.deploy(
            db,
            application_name=db,
            series=series,
        )
    return db_app


async def deploy_easyrsa_app(model, series='xenial'):
    if 'easyrsa' in model.applications:
        easyrsa_app = model.applications['easyrsa']
    else:
        easyrsa_app = await model.deploy(
            'cs:~containers/easyrsa',
            application_name='easyrsa',
            series=series,
        )
    return easyrsa_app


async def deploy_etcd_app(model, series='xenial'):
    if 'etcd' in model.applications:
        etcd_app = model.applications['etcd']
    else:
        etcd_app = await model.deploy(
            'etcd',
            application_name='etcd',
            series='xenial',
            config={'channel': '3.1/stable'},
        )
    return etcd_app


async def add_relation(model, app_name, local_interface, remote_interface):
    for rel in model.applications[app_name].relations:
        if rel.matches(remote_interface):
            break
    else:
        app = model.applications[app_name]
        await app.add_relation(local_interface, remote_interface)


async def deploy(db, hamode):
    charm_dir = os.environ.get('VAULT_CHARM_DIR')
    assert charm_dir, print(
        "Please set the environment variable VAULT_CHARM_DIR to point at the "
        "local charm")
    # Create a Model instance. We need to connect our Model to a Juju api
    # server before we can use it.
    model = Model()

    # Connect to the currently active Juju model
    await model.connect_current()

    try:
        vault_app = await deploy_vault_app(model, charm_dir)
        db_app = await deploy_db_app(model, db)
        await add_relation(
            model,
            'vault',
            relations[db]['vault_interface'],
            relations[db]['db_interface'])

        if hamode and 'easyrsa' not in model.applications:
            easyrsa_app = await deploy_easyrsa_app(model)
            etcd_app = await deploy_etcd_app(model)
            await add_relation(
                model,
                'etcd',
                'certificates',
                'easyrsa:client')
            await add_relation(
                model,
                'etcd',
                'db',
                'vault:etcd')
            await vault_app.add_units(count=2)

        await model.block_until(lambda: vault_app.status == 'active')
        await model.block_until(lambda: db_app.status == 'active')
        await model.block_until(lambda: model.all_units_idle())
        vault_app = model.applications['vault']
        vault_units = [vault_app.units[0].public_address]
        if hamode:
            vault_units.extend([
                vault_app.units[1].public_address,
                vault_app.units[2].public_address])
        vault_tests.run(units=vault_units)
    finally:
        # Disconnect from the api server and cleanup.
        await model.disconnect()


def main():
    logging.basicConfig(level=logging.INFO)

    # If you want to see everything sent over the wire, set this to DEBUG.
    ws_logger = logging.getLogger('websockets.protocol')
    ws_logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--database", choices=['mysql', 'postgresql'],
                        help="Database backend", default='postgresql')
    parser.add_argument("--hamode", choices=['etcd', None],
                        help="Database backend", default=None)
    args = parser.parse_args()

    # Run the deploy coroutine in an asyncio event loop, using a helper
    # that abstracts loop creation and teardown.
    loop.run(deploy(db=args.database, hamode=args.hamode))


if __name__ == '__main__':
    main()
