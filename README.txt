# CAdata converter

'read-data.py'

Modify according to your needs. Currently reads files that are names 'camera?-attr' and tries to find a corresponding 'camera?-data' to go along with it. Data is searched from the 'data/' folder (you will need to create it) and it is output to the 'output/' folder. 

Depends on Pillow.

## Install

Install python >=3.7 (not sure about the exact oldest compatible version).

Install Pillow:
	
	python3 -m pip install --upgrade Pillow

## Run

	python read-data.py

