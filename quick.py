#!/usr/bin/env python
# Karl Palsson, October 2014 <karlp@tweak.net.au>
# Considered to be released under your choice of MIT/Apache2/BSD 2 clause
#
# Provides generic hooks for reading/writing i2c via a CH341 in i2c/mem/epp
# mode.  Has only been _currently_ tested with a CH341A device.
import logging

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("py2c-ch34x")

import struct
import usb.core
import usb.util

# These definitions are from ch341eeprom, and from ch34x vendor serial uart driver
# They're all just magic numbers, so talk to your lawyers about who owns what
# spellings of the names.  (No debate that work was done by people to recover these
# And that was not all me)
# Oh, and it's all the same as https://code.google.com/p/usb2i2c
# the definitions are the same!
magic_read_setup = "\xaa\x74\x83\xa0\x00\x00\x74\x81\xa1\xe0\x00\x00\x06\x04\x00\x00" \
            "\x00\x00\x00\x00\x40\x00\x00\x00\x11\x4d\x40\x77\xcd\xab\xba\xdc" \
            "\xaa\xe0\x00\x00\xc4\xf1\x12\x00\x11\x4d\x40\x77\xf0\xf1\x12\x00" \
            "\xd9\x8b\x41\x7e\x00\xf0\xfd\x7f\xf0\xf1\x12\x00\x5a\x88\x41\x7e" \
            "\xaa\xe0\x00\x00\x2a\x88\x41\x7e\x06\x04\x00\x00\x11\x4d\x40\x77" \
            "\xe8\xf3\x12\x00\x14\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00" \
            "\xaa\xdf\xc0\x75\x00"

class CtrlCommands():
    """
    This is just usb standard stuff...
    """
    WRITE_TYPE = 0x40
    READ_TYPE = 0xc0

class VendorCommands():
    READ_REG = 0x95
    WRITE_REG = 0x9a
    SERIAL = 0xa1
    PRINT = 0xa3
    MODEM = 0xa4
    SPI = 0xa8
    SIO = 0xa9
    I2C = 0xaa
    UIO = 0xab
    VERSION = 0x5f # at least in serial mode?

class I2CCommands():
    # These are all from ch341dll.h, mostly untested
    """
    After STA, you can insert MS|millis, and US|usecs to insert a delay
    (you can insert multiple)
    MS|0 = 250ms wait,
    US|0 = ~260usecs?
    US|10 is ~10usecs,
    be careful, US|20 = MS|4!  US|40 = ? (switched back to 20khz mode)
    """
    STA = 0x74
    STO = 0x75
    OUT = 0x80
    IN = 0xc0
    MAX = 32 # min (0x3f, 32) ?!
    SET = 0x60 # 0 = 20
    US = 0x40 # vendor code uses a few of these in 20khz mode?
    MS = 0x50
    DLY = 0x0f
    END = 0x00 # Finish commands with this. is this really necessary?


class CH341():
    def vendor_read(self, req, wValue, wIndex, len):
        return self.dev.ctrl_transfer(CtrlCommands.READ_TYPE, req, wValue, wIndex, len)

    def __init__(self, vid=0x1a86, pid=0x5512):
        dev = usb.core.find(idVendor=vid, idProduct=pid)
        if not dev:
            raise ValueError("Device not found (%x:%x" % (vid, pid))
        log.info("Found device (%x:%x) version: %d.%d",
                 vid, pid, dev.bcdDevice >> 8, dev.bcdDevice & 0xff)
        # These devices only have one that I know of...
        assert(dev.bNumConfigurations == 1)
        dev.set_configuration()
        self.dev = dev
        # i2c vs epp vs mem mode? or is this fixed?
        log.debug("Device protocol? %d", dev.bDeviceProtocol)

        #ch34x_vendor_read( VENDOR_VERSION, 0x0000, 0x0000, serial, buf, 0x02 );
        #static int ch34x_vendor_read( __u8 request,__u16 value,  __u16 index,
        #                struct usb_serial *serial, unsigned char *buf, __u16 len )
        #retval = usb_control_msg( serial->dev, usb_rcvctrlpipe(serial->dev, 0),
        #                request, VENDOR_READ_TYPE, value, index, buf, len, 1000 );
        vv = self.vendor_read(VendorCommands.VERSION, 0, 0, 2)
        log.info("vendor version = %d.%d (%x.%x)", vv[0], vv[1], vv[0], vv[1])

    def set_speed(self, speed=100):
        """
        Set the i2c speed desired
        :param speed: in khz, will round down to 20, 100, 400, 750
        :return: na
        20 and 100 work well, 400 is not entirely square, but I don't think it's meant to be
        750 is closer to 1000 for bytes, but slower around acks and each byte start.
        All seem to work well.
        """
        sbit = 1
        if speed < 100:
            sbit = 0
        elif speed < 400:
            sbit = 1
        elif speed < 750:
            sbit = 2
        else:
            sbit = 3

        # TODO ^ how does linux handle this sort of stuff normally?
        # logging when it doesn't match?
        cmd = [VendorCommands.I2C, I2CCommands.SET | sbit, I2CCommands.END]
        count = self.dev.write(2, cmd)
        assert count == len(cmd), "Failed to write cmd to usb"

    def eeprom_read(self, address, start, count):
        """
        Issue an i2c read (single byte addressing, 24cxx styleee)
        :param address: the i2c address of the eeprom
        :param start: the starting address to read from
        :param count: how many bytes to read
        :return:
        """
        # HACK ALERT - still decodign the i2c read/write stuff
        if start > 0x7ff:
            raise ValueError("Can't handle > 16k devices yet")
        len_write = 2 # for 24c01/24c02, address is one byte
        # for up to 16k, this fits in
        eep_cmd = [address | (start >> 7) & 0x0e, (start & 0xff)]
        cmd = [VendorCommands.I2C,
               I2CCommands.STA,
               # waits can be inserted here
               I2CCommands.OUT | len(eep_cmd),
               ] + eep_cmd
        cmd += [I2CCommands.STA,
                # Waits can be inserted here too
                I2CCommands.OUT | 1, address | 1] # Write address
        if (count <= 32):
            cmd += [I2CCommands.IN | count - 1]
            cmd += [I2CCommands.IN, I2CCommands.STO, I2CCommands.END]
            log.debug("writing: %s", [hex(cc) for cc in cmd])
            cnt = self.dev.write(2, cmd)
            assert(cnt == len(cmd))
            q = self.dev.read(0x82, count)
            return q
        else:
            raise ValueError("Can't handler reads longer than 32 bytes yet")


if __name__ == "__main__":
    q = CH341()
    q.set_speed(100)
    x = q.eeprom_read(0xa0, 0, 8)
    print([hex(z) for z in x])
    log.info("received: %d bytes: %s", len(x), x)
