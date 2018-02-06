#!/bin/bash

UNITS=$(juju status vault | awk '/^vault\// {print $5}' | paste -s -d ' ')
for u in $UNITS; do
    echo -e "\n** $u ** "
    export VAULT_ADDR=http://${u}:8200; vault $@
done
