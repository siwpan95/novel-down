#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""包入口：python -m noveldown ..."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
