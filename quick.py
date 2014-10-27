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
    MEMW = 0xa6 # aka mCH341_PARA_CMD_W0
    MEMR = 0xac # aka mCH341_PARA_CMD_R0
    SPI = 0xa8
    SIO = 0xa9
    I2C = 0xaa
    UIO = 0xab
    I2C_STATUS = 0x52
    I2C_COMMAND = 0x53
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
    MAX = 32 # min (0x3f, 32) ?! (wrong place for this)
    SET = 0x60 # bit 7 apparently SPI bit order, bit 2 spi single vs spi double
    US = 0x40 # vendor code uses a few of these in 20khz mode?
    MS = 0x50
    DLY = 0x0f
    END = 0x00 # Finish commands with this. is this really necessary?

class PinState():
    """
    This is kinda gross, should be a more pythonic way of doing this?
    I've verified this works on a few pins, not sure about all of them, d7..d0 work.

    """
    ERR = 0x100 # read-write
    PEMP = 0x200 # read-write
    INT = 0x400 # read-write
    SLCT = 0x800 # read-write
    WAIT = 0x2000 # read-write
    DATAS = 0x4000 # "write readable only" ?!
    ADDRS = 0x8000 # "write readable only" ?!
    RESET = 0x10000 # "just write"
    WRITE = 0x20000 # "just write"
    SCL = 0x400000 # read-only
    SDA = 0x800000 # read-only
    DXX = 0xff000000
    def __init__(self, bits):
        if (type(bits) != type(int)):
            # assume it's the raw field from reading i2c status
            out = struct.unpack_from(">IH", bytearray(bits))
            bits = out[0]
            # TODO - no clue what the last word is for.
        s = []
        if bits & self.ERR: s += ["ERR"]
        if bits & self.PEMP: s += ["PEMP"]
        if bits & self.INT: s += ["INT"]
        if bits & self.SLCT: s += ["SLCT"]
        if bits & self.WAIT: s += ["WAIT"]
        if bits & self.DATAS: s += ["DATAS"]
        if bits & self.ADDRS: s += ["ADDRS"]
        if bits & self.RESET: s += ["RESET"]
        if bits & self.WRITE: s += ["WRITE"]
        if bits & self.SCL: s += ["SCL"]
        if bits & self.SDA: s += ["SDA"]
        if bits & self.DXX:
            datax = (bits & self.DXX) >> 24
            for i in range(8):
                if (1<<i) & datax:
                    s += ["D%d" % i]
        self.as_bits = bits
        self.names = s

    def __str__(self):
        return "Pins[" + ",".join(self.names) + "]"

class CH341():
    """
    TODO - make this behave more like python-smbus. (be as api compat as possible!)
    """
    EP_OUT = 2
    EP_IN = 0x82

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
        iss = self.vendor_read(VendorCommands.I2C_STATUS, 0, 0, 8)
        log.debug("i2c status = %s, pins = %s", iss, PinState(iss))

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
        count = self.dev.write(self.EP_OUT, cmd)
        assert count == len(cmd), "Failed to write cmd to usb"

    def i2c_start(self):
        """
        Just a start bit...
        :return:
        """
        cmd = [VendorCommands.I2C, I2CCommands.STA, I2CCommands.END]
        log.debug("writing: %s", [hex(cc) for cc in cmd])
        cnt = self.dev.write(self.EP_OUT, cmd)
        assert(cnt == len(cmd))

    def i2c_stop(self):
        # This doesn't seem to be very reliable :(
        cmd = [VendorCommands.I2C, I2CCommands.STO, I2CCommands.END]
        log.debug("writing: %s", [hex(cc) for cc in cmd])
        cnt = self.dev.write(self.EP_OUT, cmd)
        assert(cnt == len(cmd))

    def i2c_detect(self, addr):
        """
        Use the single byte write style to get an ack bit from writing to an address with no commands.
        :param addr:
        :return: true if the address was acked.
        """
        cmd = [VendorCommands.I2C,
               I2CCommands.STA, I2CCommands.OUT, addr, I2CCommands.STO, I2CCommands.END]
        log.debug("writing: %s", [hex(cc) for cc in cmd])
        cnt = self.dev.write(self.EP_OUT, cmd)
        assert(cnt == len(cmd))
        rval = self.dev.read(self.EP_IN, I2CCommands.MAX)
        assert(len(rval) == 1)
        return not (rval[0] & 0x80)

    def i2c_write_byte_check(self, bb):
        """
        write a byte and return the ack bit
        :param bb: byte to write
        :return: true for ack, false for nak
        """
        cmd = [VendorCommands.I2C, I2CCommands.OUT, bb, I2CCommands.END]
        log.debug("writing: %s", [hex(cc) for cc in cmd])
        cnt = self.dev.write(self.EP_OUT, cmd)
        assert(cnt == len(cmd))
        rval = self.dev.read(self.EP_IN, I2CCommands.MAX)
        assert(len(rval) == 1)
        return not (rval[0] & 0x80)
        log.debug("read in %s", rval)

    def i2c_read_block(self, length):
        """
        Requests a read of up to 32 bytes
        :return: array of data
        """
        # not sure why/if this needs a -1 like I seemed to elsewhere
        #cmd = [VendorCommands.I2C, I2CCommands.IN | length, I2CCommands.END]
        cmd = [VendorCommands.I2C, I2CCommands.IN, I2CCommands.END]
        cnt = self.dev.write(self.EP_OUT, cmd)
        assert(cnt == len(cmd))
        rval = self.dev.read(self.EP_IN, I2CCommands.MAX)
        print(len(rval), length)
        log.debug("read in %s", rval)
        return rval

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
            if count > 1: # ie, only include the IN|len if you have something to | in.
                cmd += [I2CCommands.IN | count - 1]
            cmd += [I2CCommands.IN, I2CCommands.STO, I2CCommands.END]
            iss = self.vendor_read(VendorCommands.I2C_STATUS, 0, 0, 8)
            log.debug("i2c status = %s, pins = %s", iss, PinState(iss))
            log.debug("writing: %s", [hex(cc) for cc in cmd])
            cnt = self.dev.write(self.EP_OUT, cmd)
            assert(cnt == len(cmd))
            iss = self.vendor_read(VendorCommands.I2C_STATUS, 0, 0, 8)
            log.debug("i2c status = %s, pins = %s", iss, PinState(iss))
            q = self.dev.read(self.EP_IN, count)
            return q
        else:
            # need a 32 byte pad block and 	memset(buf, 0x55, sizeof(buf));
#[aa][e0][00][00][00][00][00][00][00][00][00][00][00][00][00][00]
#[00][00][00][00][00][00][00][00][00][00][00][00][00][00][00][00]
            # for every chunk.
            cmd += [I2CCommands.IN | 32] # 0xe0
            cmd += [0 for x in range(32 - len(cmd))] # pad to start of next 32?

            cmd += [VendorCommands.I2C]
            if count - 1 - 32 > 0:
                cmd += [I2CCommands.IN | (count - 1 - 32)]
            cmd += [I2CCommands.IN, I2CCommands.STO, I2CCommands.END]

            cnt = self.dev.write(self.EP_OUT, cmd)
            assert(cnt == len(cmd))
            read_count = 0
            rval = []
            # reads need to be in chunks of up to 32.
            while read_count < count:
                q = self.dev.read(self.EP_IN, count - read_count)
                read_count += len(q)
                rval += q

            return rval


# them 64 0x40 (same as me)
#0000   aa 74 82 a0 00 74 81 a1 e0 00 12 00 02 00 00 00
#0010   01 00 00 00 24 e1 12 00 34 00 30 00 00 00 00 00
#0020   aa df c0 75 00
#them 65 0x41
#0000   aa 74 82 a0 00 74 81 a1 e0 00 12 00 02 00 00 00
#0010   01 00 00 00 24 e1 12 00 2e e1 12 00 02 00 00 00
#0020   aa e0 00 00 e8 ee 97 7c 00 00 00 00 17 a8 42 73
#0030   1e 00 00 00 e8 ee 97 7c cc 3e c8 00 00 00 00 00
#0040   aa c0 75 00
# my 65
#0000   aa 74 82 a0 00 74 81 a1 e0 00 00 00 00 00 00 00
#0010   00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
#0020   aa e0 c0 75 00

#them 66
#0000   aa 74 82 a0 00 74 81 a1 e0 00 12 00 02 00 00 00
#0010   01 00 00 00 24 e1 12 00 2e e1 12 00 02 00 00 00
#0020   aa e0 00 00 e8 ee 97 7c 00 00 00 00 17 a8 42 73
#0030   1e 00 00 00 e8 ee 97 7c cc 3e c8 00 00 00 00 00
#0040   aa c1 c0 75 00

#them 0x80 (setup, then aa e0 at 32bytes pads, til the regular trailer
#0000   aa 74 82 a0 00 74 81 a1 e0 00 12 00 02 00 00 00
#0010   01 00 00 00 24 e1 12 00 2e e1 12 00 02 00 00 00
#0020   aa e0 00 00 e8 ee 97 7c 00 00 00 00 17 a8 42 73
#0030   1e 00 00 00 e8 ee 97 7c 35 04 91 7c 00 00 00 00
#0040   aa e0 00 00 3c 00 08 02 35 04 91 7c 3e 04 91 7c
#0050   d0 e3 12 00 24 00 02 00 a0 e1 12 00 02 00 00 00
#0060   aa df c0 75 00
#usbi2c read 0x80
#writing 101 bytes, read_step = 32, read times = 4
#[aa][74][82][a0][00][74][81][a1][e0][00][00][00][00][00][00][00]
#[00][00][00][00][00][00][00][00][00][00][00][00][00][00][00][00]
#[aa][e0][00][00][00][00][00][00][00][00][00][00][00][00][00][00]
#[00][00][00][00][00][00][00][00][00][00][00][00][00][00][00][00]
#[aa][e0][00][00][00][00][00][00][00][00][00][00][00][00][00][00]
#[00][00][00][00][00][00][00][00][00][00][00][00][00][00][00][00]
#[aa][df][c0][75][00]

def test_manual(q):
    q.i2c_start()
    print(q.i2c_write_byte_check(0xa0))
    print(q.i2c_write_byte_check(0x00))
    q.i2c_start()
    print(q.i2c_write_byte_check(0xa1))
    data = q.i2c_read_block(6)
    print([hex(z) for z in data])
    q.i2c_stop()

def scan(q):
    results = []
    for i in range(250):
        r = q.i2c_detect(i)
        print("address: %d (%#x) is: %s" % (i, i, r))
        if r: results += [i]
    print("Responses from i2c devices at: ", results, [hex(a) for a in results])


if __name__ == "__main__":
    q = CH341()
    q.set_speed(400)
    #x = q.eeprom_read(0xa0, 0, 65)
    #print([hex(z) for z in x])
    #log.info("received: %d bytes: %s", len(x), x)
    #test_manual(q)
    scan(q)
