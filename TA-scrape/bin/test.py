#!/usr/bin/env python
from __future__ import print_function
import os
import sys

LIB_DIR = os.path.join(os.path.join(os.path.dirname(__file__), ".."), "lib")

if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

try:
    from time import sleep, time
    from splunklib.searchcommands import (
        dispatch,
        GeneratingCommand,
        Configuration,
        Option,
        validators,
    )
except Exception as e:
    exit()


@Configuration(type="events", retainsevents=True, streaming=False)
class TestCommand(GeneratingCommand):

    def generate(self):

        yield {"_time": time(), "_raw": "Hello there"}
        
        # print("hello there")
        # if sys.version_info >= (3, 0):
        #     yield {"_time": time(), "_raw": "version 3.x"}
        # else:
        #    yield {"_time": time(), "_raw": "version 2.x"}


dispatch(TestCommand, sys.argv, sys.stdin, sys.stdout, __name__)
