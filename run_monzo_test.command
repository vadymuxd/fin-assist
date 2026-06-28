#!/bin/bash
cd "/Users/vadymshcherbakov/Documents/Claude/Fin Assist"
python3 scripts/monzo_smoke_test.py 2>&1 | tee scripts/monzo_test_output.txt
