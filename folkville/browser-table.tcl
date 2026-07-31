# Folkville's table manifest — everything browser-table needs to know about
# this app. See browser-table/README.md for the format.
#
#   FOLK_TABLE=$PWD/folkville/browser-table.tcl

display 1200 760

program folkville.folk

#    kind       label           program                    x     y   [off]
card bulldozer "BULLDOZER"   folkville-bulldozer.folk     200   600
card paver     "ROAD PAVER"  folkville-paver.folk         400   600
card crane     "CRANE"       folkville-crane.folk         600   600
card reset     "RESET WORLD" folkville-reset.folk        1080    80  off
