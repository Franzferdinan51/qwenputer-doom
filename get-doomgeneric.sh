#!/bin/sh
# Fetch doomgeneric at the commit this port was built against.
set -e
if [ ! -d doomgeneric ]; then
  git clone https://github.com/ozkl/doomgeneric doomgeneric
fi
git -C doomgeneric checkout e257a09527062bfb986b6e5e0780839b6cbd5b71
