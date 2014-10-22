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

Lots more datasheets and links down a bit on this thread:
http://www.kenotrontv.ru/forum/topic/199-usb-%D0%BF%D1%80%D0%BE%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%B0%D1%82%D0%BE%D1%80-%D0%B4%D0%BB%D1%8F-flash-%D0%B8-eeprom-usb-bus-convert-chip-ch341/
