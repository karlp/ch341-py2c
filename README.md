pyusb wrappers for using a ch341 in i2c mode.

Somewhat based on git@github.com:commandtab/ch341eeprom.git but more openended,
and not feeling the need to do everything in C.

usb2i2c: https://code.google.com/p/usb2i2c/ seems to be identical protocols,
possibly earlier versions of the same chips. (And there's code available!
whee!)

Interesting ideas on directly getting/setting the status of the pins via
"CH341GetInput"/"CH341SetOutput" see if that method is in the usb2i2c code?
http://common-codebase.googlecode.com/svn-history/r70/trunk/others/python_test/i2c/CH341.py

More links here:
https://hackingbtbusinesshub.wordpress.com/category/ch341/

