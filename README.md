# SRSL-runway-data-generator
A runway data generator for the SmartRunway, SmartLanding addon for Aerowinx PSX

See https://aerowinx.com/board/index.php/topic,7976.0.html

As far as understand, using your own Navigraph subscription to
download their nav data and then using that data in your own flight
sim for non-professtional use is not against the Navigraph TOS.

However, you need to decide this for yourself before using this
tool. See e.g
https://developers.navigraph.com/docs/general/restrictions


## Usage

- Download the database in Litte NavMap format from https://navigraph.com/downloads
- Unzip the file to get the little_navmap_navigraph.sqlite file
- Run add_airports.py

Example (generate a database with all runways longer than 1800m):

``` text
$ python3 add_airports.py --database=little_navmap_navigraph.sqlite --generate-longer-than=1800 --output-file=Runways.data
```

If you want to keep the hand-crafted data that is provided in SRSL,
you can tell the script to exclude those airports:

``` text
$ python3 add_airports.py --database=little_navmap_navigraph.sqlite --generate-longer-than=1800 --output-file=Runways.data --override-database=Runways.data.ORIG
```

Then copy the generated Runways.data to your SRSL installation and
restart SRSL.
