import smbus3
import logging

def write_bit(inbyte: int, bit: int, value: (bool|int)) -> int:
    if value:
        inbyte |= (1 << bit)
    else:
        inbyte &= ~(1 << bit)
    return inbyte


class PCA9557:
    REG_INP = 0
    REG_OUT = 1
    REG_INV = 2
    REG_DIR = 3
    DIR_IN = 1
    DIR_OUT = 0

    def __init__(self, bus: smbus3.SMBus, address: int):
        self.logger = logging.getLogger(__name__ + f"(0x{address:02X})")
        self.logger.debug(f"Initializing PCA9557")
        self.bus = bus
        self.address = address
        # default values after reset:
        self.conf = 0b11111111
        self.out = 0b00000000
        self.inv = 0b11110000

        # set all pins to non-inverted inputs
        self.write_inv(0b00000000)
        self.write_direction(0b11111111)

    def value(self, pin: int, value: int = None) -> int:
        if value is not None:
            self.logger.debug(f"Setting Pin {pin} to {'high' if value else 'low'}")
            self.out = write_bit(self.out, pin, value)
            self.write_output()
        else:
            self.logger.debug(f"Reading value from Pin {pin}")
            value = self.read_pin(pin)
        return value

    def direction(self, pin: int, direction: int) -> int:
        self.logger.debug(f"Setting Pin {pin} to {'input' if direction else 'output'}")
        self.conf = write_bit(self.conf, pin, direction)
        self.write_direction()
        return direction

    def invert(self, pin: int, inverted: int) -> int:
        self.logger.debug(f"Setting Pin {pin} to {'inverted' if inverted else 'non-inverted'}")
        self.inv = write_bit(self.inv, pin, inverted)
        self.write_inv()
        return inverted

    def read_pin(self, pin: int) -> int:
        value = (self.read() >> pin) % 2
        return value

    def write_inv(self, inv: int = None) -> None:
        if inv is None:
            inv = self.inv
        self.logger.debug(f"Setting Polarity inversion register to 0b{inv:08b}")
        self.bus.write_byte_data(self.address, self.REG_INV, inv)
        self.inv = inv

    def write_direction(self, direction: int = None) -> None:
        if direction is None:
            direction = self.conf
        self.logger.debug(f"Setting Configuration Register to 0b{direction:08b}")
        self.bus.write_byte_data(self.address, self.REG_DIR, direction)
        self.conf = direction

    def write_output(self, outputs: int = None) -> None:
        if outputs is None:
            outputs = self.out
        self.logger.debug(f"Setting Output port Register to 0b{outputs:08b}")
        self.bus.write_byte_data(self.address, self.REG_OUT, outputs)
        self.out = outputs

    def read(self) -> int:
        inputs = self.bus.read_byte_data(self.address, self.REG_INP)
        self.logger.debug(f"Read Input port Register: {inputs:08b}")
        return inputs
