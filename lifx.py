import struct, socket
import cmd
import subprocess
import time
import sys
import collections
# from collections import namedtuple
import itertools
from utils import mainp
import utils
from colors import color_names

# payload = namedtuple("payload", "protocol message format data")

# Use these to avoid the discovery protocol.
lifx1 = '10.1.0.83'
lifx2 = '10.1.0.84'

class Bulb:
	SOURCE = 0x314
	seq = itertools.cycle(range(256))

	def __init__(self,mac,ip,port):
		self.mac = mac
		self.ip = ip
		self.port = port
		self.source = SOURCE
		self.sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
		self.sock.settimeout(3)

	def send(self,payload_type,payload_fmt='',*payload,response=True,**kwargs):
		sequence = next(Bulb.seq)
		packet = make_lifx_packet(self.mac,sequence,payload_type,payload_fmt,*payload,**kwargs)
		self.sock.sendto(packet, (self.ip,self.port))
		buf_size = 128
		if response:
			try:
				resp = self.sock.recv(buf_size)
				return parse_lifx_packet(resp)
			except socket.timeout:
				return None, None
		else:
			return None, None

	def __eq__(self,other):
		return self.mac == other.mac

	def __hash__(self):
		return hash(self.mac)

	def __repr__(self):
		return "Bulb({:X}>,{},{})".format(self.mac,
		 self.ip, self.port)

	def __format__(self, fmt):
		return "<{:X} @ {}:{}>".format(self.mac,self.ip,self.port)

	def get_power_state(self):
		_, resp = self.send(GET_POWER_STATE)
		value, = struct.unpack('<H',resp)
		return bool(value)
		
	def set_power_state(self,state):
		if state:
			_, resp = self.send(SET_POWER_STATE, 'H', 0xffff)
		else:
			_, resp = self.send(SET_POWER_STATE, 'H', 0x0000)

		state, = struct.unpack('<H',resp)
		return state

	def read_light_status(self,resp):
		hue, sat, bri, kel = struct.unpack('<HHHH',resp[:8])
		print("color is hue={:#06x}, sat={:#06x}, bri={:#06x}, kel={:#06x}"
				.format(hue, sat, bri, kel))

	def get_hsbk(self):
		_, resp = self.send(GET_HSBK)
		return struct.unpack("<HHHH", resp[:8])

	def set_hsbk_raw(self, hue, sat, bri, kel, dur=0):
		_, resp = self.send(SET_HSBK, 'xHHHHI', hue, sat, bri, kel, dur)

	def set_hsbk(self, hue, sat=1, bri=1, kel=3500, dur=0):
		assert 0 <= hue <= 360, "hue must satisfy 0 <= hue <= 360"
		hue = round(0xffff*hue/360)
		assert 0 <= sat <= 1, "saturation must satisfy 0 <= sat <= 1"
		sat = round(0xffff*sat)
		assert 0 <= bri <= 1, "brightness must satisfy 0 <= bri <= 1"
		bri = round(0xffff*bri)
		assert 2500 <= kel <= 9000, "kelvin must satisfy 2500 <= kel <= 9000"

		return self.set_hsbk_raw(hue,sat,bri,kel,dur)

	def set_rgbw_raw(self,red,green,blue,white=2500):
		_, resp = self.send(SET_RGBW, 'HHHH', red, green, blue, white, response = False)

	def set_rgbw(self,red=0,green=0,blue=0,white=2500):
		assert 0 <= red <= 1, "red must satisfy 0 <= red <= 1"
		red = round(0xffff*red)
		assert 0 <= green <= 1, "green must satisfy 0 <= green <= 1"
		green = round(0xffff*green)
		assert 0 <= blue <= 1, "blue must satisfy 0 <= blue <= 1"
		blue = round(0xffff*blue)
		# assert 0 <= white <= 9000, "white must satisfy 2500 <= white <= 9000"

		return self.set_rgbw_raw(red, green, blue, white)


"""
Header Format
| - FRAME
| SIZE 									(2) H
| ORIGIN TAGGED ADDRESSABLE PROTOCOL 	(2) H
| SOURCE  								(4) I
| - FRAME ADDRESS
| TARGET 								(8) Q 
| RESERVED 								(6) 6x
| ACK/RESP REQ 				                  		(1) B
| SEQUENCE 								(1) B
| - PROTOCOL HEADER
| RESERVED 								(8) 8x
| TYPE 									(2) H
| RESERVED 								(2) 2x

"""

header_fmt = '<HHIQ6xBB8xH2x'

SOURCE = 0x314
RESPONSE = 0x1
DEFAULT_PORT = 56700

# protocol types for frame
DISCOVERY = 0x3400
COMMAND = 0x1400

# packet types for commands
GET_SERVICE = 0x02
GET_POWER_STATE = 0x14
SET_POWER_STATE = 0x15
GET_HSBK = 0x65
SET_HSBK = 0x66
SET_RGBW = 0x6a

def make_lifx_packet(target,sequence,payload_type,payload_fmt,*payload,
		protocol=COMMAND,
		source=SOURCE,
		response=True):
	packet_fmt = header_fmt + payload_fmt
	size = struct.calcsize(packet_fmt)
	return struct.pack(packet_fmt, size, protocol, source, target, response, sequence, payload_type, *payload)

def parse_lifx_packet(packet):
	header_size = struct.calcsize(header_fmt)
	return struct.unpack(header_fmt,packet[:header_size]), packet[header_size:]

def bytestohex(bytestr):
	return "".join("{:02X}".format(byte) for byte in bytestr)


def readheader(header):
	fields = (("SIZE",2), ("OTAP",2), ("SOURCE",4), ("TARGET",8), ("ACKRESP",1), ("SEQUENCE",1), ("TYPE",2))
	for (field,size), value in zip(fields, header):
            print("","{field:<10} = {value:#0{size}x}".format(field=field, size=2+2*field, value=value))

def bound(x,lo,hi):
	if x > hi:
		return hi
	elif x < lo:
		return lo
	else:
		return x

def discover(ip = '<broadcast>'):
	packet = make_lifx_packet(0,0,GET_SERVICE,"",protocol=DISCOVERY)
	sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
	sock.settimeout(5)
	sock.sendto(packet, (ip,DEFAULT_PORT))
	resp = sock.recv(struct.calcsize(header_fmt+"BI"))
	header, resp_payload = parse_lifx_packet(resp)
	service, port = struct.unpack("<BI",resp_payload)
	mac = header[3]
	return Bulb(mac,ip,port)

def discoverall():
	return subprocess.check_output(["lifxdiscover.bat"]
		).decode('utf-8'
		).split()

test = Bulb(1, 'localhost', 9999)

class LifxShell(cmd.Cmd):
	intro = \
	"""
	Welcome to the lifx command center.
	Type 'help' or '?' to see a list of commands.
	"""
	prompt = ">"
	file = None

	def __init__(self,*args,**kwds):
		self._bulbs = {}
		self.dur = 0
		super().__init__(*args,**kwds)

	@property
	def bulbs(self):
		return self._bulbs.values()

	def bulb(self,name):
		return self._bulbs[name]

	def parsecolor(self, colorname):
		colorname = colorname.lower()
		return color_names.get(colorname, (None, None, None))

	def do_add(self, arg):
		"""
		Add a bulb to the list of bulbs the commands modify.
		The bulbs are active by default.

		usage: add <NAME> <IP>, <NAME> <IP>, ...
		examples:
		>add 127.0.0.1
		Found <DEADBEEF00 @ 127.0.0.1:9999>
		>add 1.2.3.4
		No bulb found at address <1.2.3.4>
		>add this 127.0.0.1, that 1.2.3.4
		Found <DEADBEEF00 @ 127.0.0.1:9999>
		No bulb found at address <1.2.3.4>
		"""
		def nextname():
			name = 0
			while name in self._bulbs:
				name += 1
			return name

		for inp in (s.split() for s in arg.split(',') ):
			name = None
			if len(inp) == 1:
				ip, = inp
			elif len(inp) == 2:
				name, ip = inp
			else:
				print("Bad input. Format is add <NAME> <IP>, ...")
				return

			try:
				bulb = discover(ip)
				print("Found {}".format(bulb))
			except socket.timeout:
				print("No bulb found at address: <{}>".format(ip))
				continue
			except socket.gaierror:
				print("Bad input. Format is add <NAME> <IP>, ...")
				return

			# Automatically assign names to unnamed bulbs
			if name is None:
				name = nextname()

			if bulb not in self.bulbs:
				self._bulbs[name] = bulb

	def do_remove(self, arg):
		"""
		Remove a bulb to the list of bulbs the commands modify.
		
		usage: remove <NAME>
		"""
		try:
			del self._bulbs[name]
		except KeyError:
			print("No bulb with that name.")

	def do_bulbs(self, arg):
		"""
		List all active bulbs modified by this shell.
		"""
		for name,bulb in self._bulbs.items():
			print("{}: {}".format(name, bulb))

	def do_color(self, arg):
		"""
		Set bulb color by name.
		use with no argument to print the color state.

		usage: color <name> OR color
		examples:
		>color blue
		>color cerulean blue
		>color lime green
		>color cerise
		>color alien armpit
		>color minion yellow
		"""
		colorname = arg
		if not colorname:
			for bulb in self.bulbs:
				hue, sat, bri, kel = bulb.get_hsbk()
				print("<{}>: hue = {:.2f}, sat = {:.2f}, bri = {:.2f}, kel = {}".format(
					bulb.ip, hue*360/0xffff, sat/0xffff, bri/0xffff, kel))
		else:
			hue, sat, bri = self.parsecolor(colorname)
			if hue is None:
				print("No color with that name.")
				return
			for bulb in self.bulbs:
				bulb.set_hsbk(hue, sat, bri)

	def complete_color(self,text,line,begidx,endidx):
		""" Naive color complete. """
		return [s for s in color_names.keys() if text in s]

	def do_power(self, arg):
		"""
		get and modify power state.

		usage: power <state> OR power
		examples
		>power
		<1.2.3.4> is ON.
		<5.6.7.8> is OFF.
		>power on
		<1.2.3.4> is ON.
		<5.6.7.8> is ON.
		"""
		for bulb in self.bulbs:
			if not arg:
				on = bulb.get_power_state()
				print("<{}>: {}.".format(bulb.ip,"ON" if on else "OFF"))
			elif arg == "on":
				bulb.set_power_state(True)
			elif arg == "off":
				bulb.set_power_state(False)

	def do_bri(self, arg):
		"""
		Change only the brightness of light. Relative or absolute.

		usage: bri <value> OR bri +<value> OR bri -<value>
		examples:
		>bri 0.2
		<brightness is 0.2>
		bri +0.2
		<brightness is 0.4>
		bri +1
		<brightness is 1.0 (max)>
		"""
		if arg[0] in '+-':
			bri = float(arg)
			bri = round(0xffff*bri)
			for bulb in self.bulbs:
				hue, sat, old_bri, kel = bulb.get_hsbk()
				bulb.set_hsbk_raw(hue, sat, bound(old_bri + bri, 0, 0xffff), kel, self.dur)
		else:
			bri = float(arg)
			assert 0 <= bri <= 1, "brightness must satisfy 0 <= bri <= 1"
			bri = round(0xffff*bri)
			for bulb in self.bulbs:
				hue, sat, _, kel = bulb.get_hsbk()
				bulb.set_hsbk_raw(hue, sat, bri, kel, self.dur)

	def do_sat(self, arg):
		"""
		Change only the saturation of light. Relative or absolute.

		usage: sat <value> OR sat +<value> OR sat -<value>
		examples:
		>sat 0.2
		<saturation is 0.2>
		sat +0.2
		<saturation is 0.4>
		sat +1
		<saturation is 1.0 (max)>
		"""

		if arg[0] in '+-':
			sat = float(arg)
			sat = round(0xffff*sat)
			for bulb in self.bulbs:
				hue, old_sat, bri, kel = bulb.get_hsbk()
				bulb.set_hsbk_raw(hue, bound(old_sat + sat, 0, 0xffff), bri, kel, self.dur)
		else:
			sat = float(arg)
			assert 0 <= sat <= 1, "saturation must satisfy 0 <= sat <= 1"
			sat = round(0xffff*sat)
			for bulb in self.bulbs:
				hue, _, bri, kel = bulb.get_hsbk()
				bulb.set_hsbk_raw(hue, sat, bri, kel, self.dur)

	def do_hue(self, arg):
		"""
		Change only the hue of light. Relative or absolute.
		Value wraps at 360.

		usage: hue <value> OR hue +<value> OR hue -<value>
		examples:
		>hue 20
		<hue is 20>
		hue 340
		<hue is 340>
		hue +50
		<hue is 30 (340+50-360)>
		"""

		if arg[0] in '+-':
			hue = float(arg)
			hue = round(0xffff*hue/360)
			for bulb in self.bulbs:
				old_hue, sat, bri, kel = bulb.get_hsbk()
				bulb.set_hsbk_raw( (old_hue + hue) % 0xffff, sat, bri, kel, self.dur)

		else:
			hue = float(arg)
			assert 0 <= hue <= 360, "hue must satisfy 0 <= hue <= 360"
			hue = round(0xffff*hue/360)
			for bulb in self.bulbs:
				_, sat, bri, kel = bulb.get_hsbk()
				bulb.set_hsbk_raw(hue, sat, bri, kel, self.dur)

	def do_kel(self, arg):
		"""
		Change only the light temperature of the light. Relative or absolute.
		Most noticeable at low saturation values. Lower temperatures
		for more yellow-y whites, higher values for blue-ish.

		usage: kel <value> OR kel +<value> OR kel -<value>
		examples:
		>kel 
		<brightness is 0.2>
		kel +0.2
		<brightness is 0.4>
		kel +1
		<brightness is 1.0 (max)>
		"""

		if arg[0] in '+-':
			kel = int(arg)
			for bulb in self.bulbs:
				hue, sat, bri, old_kel = bulb.get_hsbk()
				bulb.set_hsbk_raw( hue, sat, bri, bound(old_kel + kel, 2500, 9000), self.dur)
		else:
			kel = int(arg)
			assert 2500 <= kel <= 9000, "Kelvin must satisfy 2500 <= kel <= 9000"
			for bulb in self.bulbs:
				hue, sat, bri, _ = bulb.get_hsbk()
				bulb.set_hsbk_raw(hue, sat, bri, kel, self.dur)

	def do_hsb(self, arg):
		'Set hue sat and bri simultaneously.'
		args = arg.split()
		while len(args) < 3:
			args.append('-')

		for bulb in self.bulbs:
			hue, sat, bri, kel = bulb.get_hsbk()

			if args[0] != '-':
				hue = float(args[0])
				assert 0 <= hue <= 360, "hue must satisfy 0 <= hue <= 360"
				hue = round(0xffff*hue/360)
			if args[1] != '-':
				sat = float(args[1])
				assert 0 <= sat <= 1, "saturation must satisfy 0 <= sat <= 1"
				sat = round(0xffff*sat)
			if args[2] != '-':
				bri = float(args[2])
				assert 0 <= bri <= 1, "brightness must satisfy 0 <= bri <= 1"
				bri = round(0xffff*bri)

			bulb.set_hsbk_raw(hue, sat, bri, kel, self.dur)

	def do_rgb(self, arg):
		'Defunct RGB setting. RGB value is stored separately from HSB.'
		r,g,b = map(lambda x: 0x100*int(x,16), arg.split())
		for bulb in self.bulbs:
			bulb.set_rgbw_raw(r,g,b)

	def do_dur(self, arg):
		'Set the default transformation time for comands.'
		dur = round(1000*float(arg))
		if dur < 0:
			print("duration in s must be positive.")
		else:
			self.dur = dur

	def do_delay(self, arg):
		""" 
		Pause executeion for given number of seconds.
		for use with input files.
		"""
		amt = float(arg)
		time.sleep(amt)

	def do_exit(self, arg):
		'Exits the interpreter.'
		return True

	def do_quit(self, arg):
		'Exits the interpreter'
		return True

	def do_EOF(self, arg):
		'Exits the interpreter.'
		return True

	def precmd(self, line):
		'Makes STDOUT much more stylish.'
		if not self.use_rawinput:
			print(line)
		return line


# class Junk(collections.UserList):
# 	def pop(self,n):
# 		print(n)
# 		k = self.data.pop(n)
# 		self.data.append(k)
# 		return k

@mainp  (str		)
def Main(file = None):
	"""
	Reads from the provided file if there is one.
	Otherwise, starts up a loop.
	"""

	try:
		if file is None:
			sh = LifxShell()
			# sh.cmdqueue = Junk(['delay 1', 'color'])
			sh.cmdloop()
		else:
			with open(file,'r') as infile:
				sh = LifxShell(stdin = infile)
				sh.use_rawinput = False
				sh.cmdloop()
	except KeyboardInterrupt as e:
		print("quit")
		sys.exit(0)
