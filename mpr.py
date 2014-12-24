# -*- coding: utf-8 -*-
import click
import requests
import os

__host = ""
__port = ""
__newrating = ""

@click.group()
@click.option('--host', envvar='MPD_RATING_HOST', type=click.STRING, default="127.0.0.1")
@click.option('--port', envvar='MPD_RATING_PORT', type=click.STRING, default="6642")
def mpr(host, port):
    global __host
    global __port
    __host = host
    __port = port
    pass

@click.command()
@click.argument('newrating', nargs=1, type=click.INT)
def rate(newrating):
    if (newrating > 0 and newrating <= 5):
        request = requests.get('http://' + __host + ':' + __port + "/addNewRating", params={'rating' : newrating})
        print("made request with rating " + str(newrating))
    pass


@click.command()
def show():
    pass

mpr.add_command(rate)
mpr.add_command(show)

if __name__ == '__main__':
    mpr()
